"""Work out what clock the Meta html exports are rendered on.

The Facebook and Instagram html exports write a local time and name no timezone beside it.
The json exports of the same account write epoch seconds, which name the instant exactly.
So an account donated in both formats answers the question directly: match a record across
the two and the difference between them is the offset the html was rendered at.

Six hand-checked records were not enough to settle it — they gave -8, 0, 0, 0, +2 and +1 —
so this runs the comparison over whole archives instead, and over as many archives as you
have.

Run it as::

    python scripts/meta_html_timezone_probe.py \\
        --json /path/to/p01_json_export --html /path/to/p01_html_export \\
        --out meta_html_offsets.csv

giving the two archives whole — a ``.zip`` or an already unpacked folder — and nothing
about what is inside them. Which files to compare is read from the extractors themselves:
every Facebook and Instagram function that builds a table with a ``Date`` or ``Timestamp``
column names the file it opens, and those are the files looked for, wherever they are
nested. The two formats file a source under different folders and the json splits some
sources across numbered parts, so files are paired on the source name alone.

Repeat ``--json`` and ``--html`` in step to compare several accounts in one run. The name
of the json export names the archive in the csv, so naming the folders after the
participant code makes the file self-describing.

Every matched record is written to the csv, one row each: which archive and file it came
from, the epoch the json recorded, that instant in UTC, the local time the html showed, and
the difference between the two. ``--summary`` additionally prints the offset and timezone
analysis; ``--verbose`` reports per file while it works.

**Nothing but dates leaves the archives.** Records are matched on the minute and second of
their timestamps, never on what they say, so no caption, name, url or search term is read
into the output. The archives are opened read-only.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    sys.exit("This needs lxml. Run it inside the project environment: poetry run python scripts/...")

try:
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:
    sys.exit("This needs Python 3.9 or newer for zoneinfo.")


#: Months by the first three letters of how they are abbreviated, lowercased, across the
#: languages these exports are written in that use Latin script. The same table the Google
#: extractor reads its html dates with, since an account writes its export in whatever
#: language it is set to and that is not always the language of the study.
MONTHS = {
    "jan": 1, "oca": 1, "ene": 1,
    "feb": 2, "şub": 2, "sub": 2,
    "mar": 3, "mrt": 3, "mär": 3, "mrz": 3,
    "apr": 4, "nis": 4, "abr": 4,
    "may": 5, "mei": 5, "mai": 5,
    "jun": 6, "haz": 6,
    "jul": 7, "tem": 7,
    "aug": 8, "ağu": 8, "agu": 8, "ago": 8,
    "sep": 9, "eyl": 9, "set": 9,
    "oct": 10, "okt": 10, "eki": 10,
    "nov": 11, "kas": 11,
    "dec": 12, "dez": 12, "ara": 12, "dic": 12,
}

#: ``Jun 26, 2026 9:05:20 am`` and ``Aug 09, 2026 9:49 am`` — the shape both exports write.
#: The seconds and the meridiem are both optional, because Instagram leaves the seconds off
#: and a 24-hour locale leaves the meridiem off. The month is matched as any run of letters
#: rather than a Latin-1 range, so that ``Şub`` and ``Ağu`` are read as well as ``Mär``.
HTML_TIMESTAMP = re.compile(
    r"^([^\W\d_]+)\.?\s+(\d{1,2}),?\s+(\d{4})[\s,]+(\d{1,2}):(\d{2})(?::(\d{2}))?"
    r"(?:\s*([AaPp])\.?[Mm]\.?)?$",
    re.UNICODE,
)

#: Keys the json exports record an epoch under.
EPOCH_KEYS = ("timestamp", "creation_timestamp", "create_timestamp", "start_timestamp")

#: Seconds since the epoch that could plausibly be a social media record: 2004 to 2035.
EPOCH_RANGE = (1_072_915_200, 2_082_758_400)

#: How far apart a json instant and an html local time may be and still be the same record.
#: Every zone on earth is inside +14/-12, and a little slack is added on top.
MAX_OFFSET = timedelta(hours=15)


# --------------------------------------------------------------------------------------
# Reading an archive, whether it is a zip or a folder
# --------------------------------------------------------------------------------------

class Archive:
    """A donated export, opened read-only, whether it arrived zipped or unpacked."""

    def __init__(self, path: Path):
        self.path = path
        self._zip = zipfile.ZipFile(path) if path.is_file() else None
        if self._zip is None and not path.is_dir():
            raise SystemExit(f"Not a folder or a zip file: {path}")

    def members(self, suffix: str) -> list[str]:
        """Every file in the archive with this extension, at any depth."""
        if self._zip is not None:
            return [n for n in self._zip.namelist() if n.lower().endswith(suffix)]
        return [
            str(p.relative_to(self.path))
            for p in self.path.rglob(f"*{suffix}")
            if p.is_file()
        ]

    def read(self, name: str) -> bytes:
        if self._zip is not None:
            return self._zip.read(name)
        return (self.path / name).read_bytes()

    def close(self):
        if self._zip is not None:
            self._zip.close()


def basename(member: str) -> str:
    """The file name of an archive member, without its folders or its extension.

    The two export formats do not agree on the folder a source sits in — the json writes
    ``logged_information/search/your_search_history.json`` where the html writes
    ``your_search_history.html`` — so the file name alone is what pairs them, and the
    folders are only there to be walked through.
    """
    return os.path.splitext(os.path.basename(member.replace("\\", "/")))[0]


#: A source Meta split across several files, ``likes_and_reactions_1.json`` and its
#: numbered siblings, all belonging to the one source the extractor names.
NUMBERED = re.compile(r"^(.*?)_\d+$")


def source_of(name: str) -> str:
    """Which source a file name belongs to, with any part number taken off."""
    match = NUMBERED.match(name)
    return match.group(1) if match else name


# --------------------------------------------------------------------------------------
# Which files to compare, taken from the extractors themselves
# --------------------------------------------------------------------------------------

#: A file an extractor opens by name. The closing quote has to match the opening one, or
#: a name that carries an apostrophe — ``advertisers_you've_interacted_with.json`` — would
#: be cut short at it.
OPENS = re.compile(r"""reader\.(?:raw|json|csv)\(\s*(["'])((?:(?!\1).)+)\1""")

#: The column names that mean an extractor reads a date out of the file.
DATE_COLUMN = re.compile(r'"(Date|Timestamp)"')


def dated_sources(platforms: Path) -> tuple[set[str], list[str]]:
    """The files the Facebook and Instagram extractors read dates out of.

    Rather than keep a list here that would drift, this reads the extractors: a function
    that builds a table with a ``Date`` or ``Timestamp`` column is one that reads a date,
    and the file names it opens are the files worth comparing. Both formats are collected,
    since the json and html readers of one source are separate functions naming the same
    file with different extensions.

    Returns the source names and a note of which modules they were read from, so the caller
    can say what it is comparing.
    """
    sources: set[str] = set()
    read: list[str] = []

    for module in ("facebook.py", "instagram.py"):
        path = platforms / module
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        found = 0
        for part in re.split(r"(?=\ndef )", text):
            # Commented-out extractors trail some functions, and name files nothing opens.
            live = "\n".join(
                line for line in part.split("\n") if not line.lstrip().startswith("#")
            )
            columns = " ".join(re.findall(r"columns=\[([^\]]*)\]", live))
            if not DATE_COLUMN.search(columns):
                continue
            for _quote, opened in OPENS.findall(live):
                sources.add(source_of(basename(opened)))
                found += 1
        read.append(f"{module} ({found} files)")

    return sources, read


# --------------------------------------------------------------------------------------
# Pulling the timestamps out of each format
# --------------------------------------------------------------------------------------

@dataclass
class JsonItem:
    """An instant the json export names exactly."""
    utc: datetime


@dataclass
class HtmlItem:
    """A local time the html export shows, on a clock we are trying to identify."""
    local: datetime
    has_seconds: bool


def looks_like_epoch(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and EPOCH_RANGE[0] <= value <= EPOCH_RANGE[1]


def extract_json_items(payload) -> list[JsonItem]:
    """Every epoch in the file, wherever it is nested.

    The json exports nest differently per source — a list at the root for some, an object
    keyed by section for others, records inside ``label_values`` for the newer ones — so
    rather than encode each shape this walks the whole document and takes every value under
    an epoch key that falls in a plausible range.
    """
    items: list[JsonItem] = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in EPOCH_KEYS and looks_like_epoch(value):
                    items.append(JsonItem(datetime.fromtimestamp(value, tz=timezone.utc)))
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return items


def parse_html_timestamp(text: str) -> HtmlItem | None:
    match = HTML_TIMESTAMP.match(text.strip())
    if not match:
        return None

    month, day, year, hour, minute, second, meridiem = match.groups()
    number = MONTHS.get(month[:3].lower())
    if number is None:
        return None

    hour = int(hour)
    if meridiem:
        hour = hour % 12 + (12 if meridiem.lower() == "p" else 0)

    try:
        local = datetime(int(year), number, int(day), hour, int(minute), int(second or 0))
    except ValueError:
        return None

    return HtmlItem(local, second is not None)


def extract_html_items(data: bytes) -> list[HtmlItem]:
    """Every timestamp in the page, found by its shape rather than by its class name.

    Meta puts the date in a differently named div per source and per product, so matching
    on the text is what keeps this working across all of them.
    """
    items: list[HtmlItem] = []
    root = etree.HTML(data)
    if root is None:
        return items

    for element in root.iter():
        text = element.text
        if not text or len(text) > 40 or ":" not in text:
            continue
        item = parse_html_timestamp(text)
        if item is not None:
            items.append(item)

    return items


# --------------------------------------------------------------------------------------
# Matching a record in one format to the same record in the other
# --------------------------------------------------------------------------------------

@dataclass
class Match:
    utc: datetime
    local: datetime
    has_seconds: bool = True
    archive: str = ""
    source: str = ""

    @property
    def offset_hours(self) -> float:
        # Where the html left the seconds off, as Instagram does, comparing against the
        # full instant would report the dropped seconds as part of the offset.
        instant = self.utc.replace(tzinfo=None)
        if not self.has_seconds:
            instant = instant.replace(second=0)
        return (self.local - instant).total_seconds() / 3600


def match_items(
    json_items: list[JsonItem], html_items: list[HtmlItem], minute_shift: int
) -> list[Match]:
    """Pair the two formats up without ever looking at what a record says.

    A timezone offset is a whole number of hours in almost every zone, and a whole number
    of minutes in all of them, so the *seconds* of a record survive the conversion and the
    *minutes* survive it up to a known shift. That is enough to identify a record: take an
    html local time, and look for json instants within fifteen hours of it whose seconds —
    and whose minutes, allowing for the shift — agree. Where exactly one json record fits,
    the pair is unambiguous and is kept; where several do, it is dropped rather than
    guessed at.

    *minute_shift* covers the zones that are not a whole hour from UTC, such as India at
    +5:30 and Nepal at +5:45. The caller tries each plausible shift and keeps whichever
    produces the most self-consistent answer.
    """
    by_instant = sorted(json_items, key=lambda j: j.utc)
    instants = [j.utc.replace(tzinfo=None) for j in by_instant]

    matches: list[Match] = []
    taken: set[int] = set()
    for html in html_items:
        low = bisect.bisect_left(instants, html.local - MAX_OFFSET)
        high = bisect.bisect_right(instants, html.local + MAX_OFFSET)

        found = None
        for index in range(low, high):
            utc = by_instant[index].utc
            if (utc.minute + minute_shift) % 60 != html.local.minute:
                continue
            if html.has_seconds and utc.second != html.local.second:
                continue
            if found is not None:
                found = None  # ambiguous, so this html record is not usable
                break
            found = index

        # One json record is one html record. Where a second html record also fits a
        # json record already claimed, neither claim can be trusted, so it is dropped —
        # without this, a dense file whose html carries no seconds produces whole runs of
        # html records all pointing at one instant, and an offset invented out of them.
        if found is not None and found not in taken:
            taken.add(found)
            matches.append(Match(by_instant[found].utc, html.local, html.has_seconds))

    return matches


def best_matching(json_items: list[JsonItem], html_items: list[HtmlItem]) -> list[Match]:
    """Try each minute shift a real timezone can have and keep the most consistent."""
    best: list[Match] = []
    best_score = (-1, -1)

    for shift in (0, 30, -30, 45, -45, 15, -15):
        found = match_items(json_items, html_items, shift)
        if not found:
            continue
        # An archive is on one clock, so the right shift is the one whose matches agree
        # with each other — not merely the one that matches the most. Scoring on raw
        # count lets a quarter-hour shift win by manufacturing matches that disagree.
        agreed = Counter(round(m.offset_hours, 2) for m in found).most_common(1)[0][1]
        if (agreed, len(found)) > best_score:
            best_score, best = (agreed, len(found)), found

    return best


# --------------------------------------------------------------------------------------
# Working out which clock explains the matches
# --------------------------------------------------------------------------------------

def explains(zone, matches: list[Match]) -> int:
    """How many of the matched records this candidate clock accounts for exactly."""
    good = 0
    for match in matches:
        shown = match.utc.astimezone(zone).replace(tzinfo=None)
        if shown == match.local:
            good += 1
        elif shown.replace(second=0) == match.local.replace(second=0):
            good += 1  # the html left the seconds off, as Instagram does
    return good


def candidate_clocks() -> list[tuple[str, object]]:
    """Every named timezone, plus every fixed whole-hour offset.

    The fixed offsets are what would show up if Meta rendered on one unchanging clock —
    the widely repeated claim that these timestamps are simply UTC-8. A named zone fits
    only if the export also moves with that zone's daylight saving.
    """
    clocks: list[tuple[str, object]] = []
    for hours in range(-12, 15):
        for minutes in (0, 30, 45):
            if hours < 0 and minutes:
                offset = timedelta(hours=hours, minutes=-minutes)
                label = f"fixed UTC{hours:+d}:{minutes:02d}"
            else:
                offset = timedelta(hours=hours, minutes=minutes)
                label = f"fixed UTC{hours:+d}" + (f":{minutes:02d}" if minutes else "")
            if timedelta(hours=-12) <= offset <= timedelta(hours=14):
                clocks.append((label, timezone(offset)))
    for name in sorted(available_timezones()):
        # posix/ and right/ are duplicate trees, and localtime is whatever this machine
        # happens to be set to — none of them name a zone an account could be set to.
        if name.startswith(("posix/", "right/")) or name == "localtime":
            continue
        try:
            clocks.append((name, ZoneInfo(name)))
        except Exception:
            continue
    return clocks


@dataclass
class PairResult:
    label: str
    per_file: list[tuple[str, int, int, int]] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    #: json files found, html files found, and sources held in both formats.
    searched: tuple[int, int, int] = (0, 0, 0)


def index_by_source(archive: Archive, suffix: str) -> dict[str, list[str]]:
    """Every file of this format in the archive, gathered under the source it belongs to.

    This is the walk through the nested folders: wherever Meta has put a file, and however
    it has numbered it, it is filed here under the plain source name the extractors use.
    """
    index: dict[str, list[str]] = defaultdict(list)
    for member in archive.members(suffix):
        index[source_of(basename(member))].append(member)
    return index


def probe(
    json_path: Path, html_path: Path, label: str, sources: set[str], verbose: bool
) -> PairResult:
    """Compare the two formats of one account, source by source."""
    json_archive, html_archive = Archive(json_path), Archive(html_path)
    result = PairResult(label)

    try:
        json_index = index_by_source(json_archive, ".json")
        html_index = index_by_source(html_archive, ".html")

        # Only the sources the extractors actually read a date out of, and only where the
        # archive holds that source in both formats.
        both = sorted(sources & set(json_index) & set(html_index))
        result.searched = (len(json_index), len(html_index), len(both))

        for source in both:
            json_items: list[JsonItem] = []
            for member in sorted(json_index[source]):
                try:
                    json_items.extend(extract_json_items(json.loads(json_archive.read(member))))
                except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                    continue
            if not json_items:
                continue

            html_items: list[HtmlItem] = []
            for member in sorted(html_index[source]):
                try:
                    html_items.extend(extract_html_items(html_archive.read(member)))
                except Exception:
                    continue
            if not html_items:
                continue

            matched = best_matching(json_items, html_items)
            for match in matched:
                match.archive, match.source = result.label, source
            result.per_file.append((source, len(json_items), len(html_items), len(matched)))
            result.matches.extend(matched)

            if verbose:
                offsets = Counter(round(m.offset_hours, 2) for m in matched)
                summary = ", ".join(f"{o:+g}h x{c}" for o, c in sorted(offsets.items()))
                print(f"    {source[:44]:44} json={len(json_items):6} html={len(html_items):6} "
                      f"matched={len(matched):6}  {summary or '-'}")
    finally:
        json_archive.close()
        html_archive.close()

    return result


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------

def report(result: PairResult) -> None:
    matches = result.matches
    print(f"\n=== {result.label}")
    print(f"    files compared : {len(result.per_file)}")
    print(f"    records matched: {len(matches)}")

    if not matches:
        print("    No records could be matched. Either the two exports are of different")
        print("    accounts, or they cover different date ranges, or the html holds no")
        print("    timestamps this recognises.")
        return

    html_total = sum(html for _, _, html, _ in result.per_file)
    rate = len(matches) / html_total if html_total else 0
    if len(matches) < 20 or rate < 0.05:
        print(f"    WARNING: only {len(matches)} of {html_total} html records could be matched")
        print("    ({:.0%}). Two exports of the same account should match most of their".format(rate))
        print("    overlap, so this pair is probably two different accounts, or two")
        print("    non-overlapping date ranges. Read what follows with that in mind.")

    offsets = Counter(round(m.offset_hours, 2) for m in matches)
    print(f"    offsets seen   : ", end="")
    print(", ".join(f"{o:+g}h ({c} records)" for o, c in sorted(offsets.items())))

    by_month: dict[str, Counter] = defaultdict(Counter)
    for match in matches:
        by_month[f"{match.utc:%Y-%m}"][round(match.offset_hours, 2)] += 1
    if len(offsets) > 1:
        print("    by month (this is where daylight saving shows up):")
        for month in sorted(by_month):
            seen = ", ".join(f"{o:+g}h x{c}" for o, c in sorted(by_month[month].items()))
            print(f"        {month}  {seen}")

    span = f"{min(m.utc for m in matches):%Y-%m} to {max(m.utc for m in matches):%Y-%m}"
    print(f"    span           : {span}")

    ranked = []
    for name, clock in candidate_clocks():
        good = explains(clock, matches)
        if good:
            ranked.append((good, name))
    ranked.sort(key=lambda r: (-r[0], "/" not in r[1], r[1]))

    perfect = [name for good, name in ranked if good == len(matches)]
    print(f"    clocks that explain every matched record: {len(perfect)}")
    if perfect:
        fixed = [n for n in perfect if n.startswith("fixed ")]
        named = [n for n in perfect if not n.startswith("fixed ")]
        if fixed:
            print(f"        as a fixed offset : {', '.join(fixed)}")
        if named:
            shown = ", ".join(named[:8])
            more = f"  (+{len(named) - 8} more equivalent zones)" if len(named) > 8 else ""
            print(f"        as a named zone   : {shown}{more}")
        if len(offsets) > 1:
            print("        -> the offset changes with the season, so the export follows the")
            print("           daylight saving of the zone the account is set to.")
        else:
            print(f"        -> one offset, {next(iter(offsets)):+g}h, held across {span}.")
            if len(by_month) < 8:
                print("           That span may be too short to have crossed a clock change,")
                print("           so this does not yet rule out a zone with daylight saving.")
    else:
        best, name = ranked[0]
        print(f"        none. Closest: {name} explains {best}/{len(matches)}.")
        print("        A single archive should have a single clock, so this suggests the")
        print("        matching picked up some wrong pairs. Treat the offsets above as the")
        print("        finding and this line as a warning.")


#: The columns written for every matched record. Dates and offsets only — nothing here
#: says what a record was about, so the file can be shared and read as data.
CSV_COLUMNS = [
    "archive",         # which donated account this row came from
    "source_file",     # the file it was read out of, without its extension
    "json_epoch",      # what the json export recorded
    "utc",             # that instant, in UTC
    "html_local",      # the local time the html export showed for the same record
    "html_seconds",    # whether the html wrote seconds, or only minutes as Instagram does
    "offset_hours",    # html_local minus utc: the offset the html was rendered at
    "utc_month",       # for reading daylight saving off the file
]


def write_csv(path: Path, results: list[PairResult]) -> int:
    """Write one row per matched record, across every archive, to *path*."""
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for result in results:
            for match in sorted(result.matches, key=lambda m: (m.source, m.utc)):
                writer.writerow([
                    match.archive,
                    match.source,
                    int(match.utc.timestamp()),
                    f"{match.utc:%Y-%m-%d %H:%M:%S}",
                    f"{match.local:%Y-%m-%d %H:%M:%S}",
                    "yes" if match.has_seconds else "no",
                    f"{match.offset_hours:g}",
                    f"{match.utc:%Y-%m}",
                ])
                rows += 1
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare the json and html exports of the same account to find the "
                    "clock the html was rendered on. Writes dates and offsets to a csv "
                    "and reads no content out of the archives.",
    )
    parser.add_argument(
        "--json", dest="json_paths", action="append", required=True, metavar="ARCHIVE",
        help="The json-formatted export. A .zip or an unpacked folder; the files inside "
             "are found wherever they are nested. Repeat it, alongside --html, per account.",
    )
    parser.add_argument(
        "--html", dest="html_paths", action="append", required=True, metavar="ARCHIVE",
        help="The html-formatted export of that same account.",
    )
    parser.add_argument(
        "--platforms", type=Path,
        default=Path(__file__).resolve().parent.parent / "packages/python/port/platforms",
        help="Where the extractors live, read to decide which files hold dates worth "
             "comparing (default: %(default)s).",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("meta_html_offsets.csv"),
        help="Where to write the matched dates and their offsets (default: %(default)s).",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Also print the offset and timezone analysis, rather than only writing the csv.",
    )
    parser.add_argument("--verbose", action="store_true", help="Report per file as well.")
    args = parser.parse_args()

    if len(args.json_paths) != len(args.html_paths):
        raise SystemExit(
            f"Got {len(args.json_paths)} --json and {len(args.html_paths)} --html archives. "
            "Give one of each per account, in the same order."
        )

    sources, read_from = dated_sources(args.platforms)
    if not sources:
        raise SystemExit(
            f"Found no extractors under {args.platforms}. Point --platforms at the folder "
            "holding facebook.py and instagram.py."
        )
    print(f"Reading dates from {len(sources)} sources, per {' and '.join(read_from)}.")

    results = []
    for index, (first, second) in enumerate(zip(args.json_paths, args.html_paths), start=1):
        json_path, html_path = Path(first).expanduser(), Path(second).expanduser()
        for path in (json_path, html_path):
            if not path.exists():
                raise SystemExit(f"No such path: {path}")

        # The name of the json export identifies the archive in the csv. Naming the
        # folders after the participant code makes the file self-describing; where two
        # are named the same, the position on the command line keeps them apart.
        label = json_path.name
        if any(r.label == label for r in results):
            label = f"{label} #{index}"
        if args.verbose:
            print(f"\n--- {label}  (json: {json_path.name}, html: {html_path.name})")
        results.append(probe(json_path, html_path, label, sources, args.verbose))

    print()
    for result in results:
        html_total = sum(html for _, _, html, _ in result.per_file)
        matched = len(result.matches)
        rate = f"{matched / html_total:.0%}" if html_total else "-"
        offsets = sorted({round(m.offset_hours, 2) for m in result.matches})
        seen = ", ".join(f"{o:+g}h" for o in offsets) or "none"
        n_json, n_html, n_both = result.searched
        print(f"  {result.label[:36]:36} json files={n_json:4} html files={n_html:4} "
              f"dated sources in both={n_both:3}")
        print(f"  {'':36} matched={matched:6} of {html_total:6} html records ({rate:>4})  {seen}")
        if html_total and matched / html_total < 0.05:
            print(f"  {'':40} ^ very few matched: check these are two exports of one account")

    rows = write_csv(args.out, results)
    print(f"\nWrote {rows} matched records to {args.out}")
    print("Columns: " + ", ".join(CSV_COLUMNS))
    print("The file holds dates and offsets only, no content from the archives.")

    if args.summary:
        for result in results:
            report(result)


if __name__ == "__main__":
    main()
