"""Study-side redaction for the Google tables (algosoc-2026).

Everything here is study policy layered on top of the platform's extraction,
applied once by ``google.extraction()`` after ``run_extraction()`` returns:

- rows whose title or URL carries an explicit-content keyword are dropped from
  the four tables named in ``EXPLICIT_FILTERED_TABLES``;
- email addresses in every table's ``Title``/``Details`` columns are replaced
  by ``[email]``;
- a table left empty by the filter is removed from the result, so its id is
  absent from the donation exactly like any other empty table.

The keyword list, ``filter_explicit_content`` and ``redact_emails`` are the
study's own, carried over as written; the platform module itself stays free
of study policy so upstream updates merge cleanly.
"""

import re

import pandas as pd

import port.helpers.extraction_helpers as eh
from port.api.d3i_props import ExtractionResult

#: Table ids whose rows are dropped on an explicit-content match. The study's
#: other Google tables (YouTube, Discover, Google News) are not filtered.
EXPLICIT_FILTERED_TABLES = frozenset({
    "search_history",
    "chrome_history",
    "video_search_history",
    "ads_history",
})

#: Columns scanned for explicit content, and columns scrubbed of addresses.
EXPLICIT_COLUMNS = ["Title", "URL"]
EMAIL_COLUMNS = ["Title", "Details"]


EXPLICIT_KEYWORDS = [
      "outlook.live.com", "mail.google.com/mail", "mail.kpnmail.nl",
      "outlook.office365.com", "porn",
      "xhamster", 
      "erotic", "kinky", "fetish", "jerk off",
     "camgirl",  "hentai", "gangbang",  "femdom",
     "onlyfans", "fansly",  "threesome", "adult video", "adult movie",
     "adult escort", "prostitute", "escort service", "sex worker",
     "stripper", "strip club", "exotic dancer",
     "not safe for work", 
     
     "xvideos.com", "xnxx.com", "redtube.com", "xhamster.com", "deloris.ai",
      "tube8.com", "spankbang.com", "youjizz.com", "fapdu.com", "9xbuddy.xyz",
     "brazzers.com", "mofos.com", "naughtyamerica.com", "bangbros.com", 
      "clips4sale.com", "camsoda.com", "chaturbate.com", "casualdating1.com",
     "myfreecams.com", "livejasmin.com", "streamate.com", "bongacams.com", "deepmode.ai",
     "onlyfans.com", "adultfriendfinder.com", "sextube.com", "beeg.com", "akg01.com",
      "xtube.com", "slutload.com", "tnaflix.com", 
     "javhd.com", "realitykings.com", "metart.com", "eroprofile.com", "nudelive.com",
     "fantasti.cc", "hclips.com", "ashemaletube.com", 
     "playvid.com", "4tube.com", "javfinder.com",  "sex.com", "hentaigasm.com",
     "hentaistream.com", "adulttime.com", "wicked.com", "dogfartnetwork.com", "stripchat.com",
     "keezmovies.com", "xempire.com", 
     "thumzilla.com", "madthumbs.com", "drtuber.com", 
     "fapdu.com", "freeones.com", "twistys.com", "3movs.com",  "candy.ai",
   "recurbate.com", "tubegalore.com",
    "lobstertube.com", "nuvid.com", "sexvid.xxx",
     "xhamsterlive.com", "playboy.tv", "cams.com", "badoinkvr.com", 
     "vrcosplayx.com", "metartx.com", "hegre-art.com", "joymii.com", 
     "spankwire.com", "tingo.ai",
       "boy18tube.com",	
       "fapnfuck.com",
       "fetishbank.net",
       "gonzoxxxmovies.com",
       "ixxx.com",
       "webcamsex.nl",
     
     "jizzbunker.com", "eporner.com", "cam4.com", "sexier.com", "adultempire.com", "basedlabs.ai",
     "joysporn.com", "slutroulette.com", "bigxvideos.com", "hotmovs.com", 

     "siswet", "taylor sands", "naughty celeste",
     "natasha nice", "angela white", "joey mills", "austin young",
     "legrand wolf", "viktor rom", "malik delgaty", "daisy taylor",
     "esluna love", "romy indy", "zara whites", "yasie lee", "tracy oba",
     "nathalie kitten", "sebriena star", "tanya de vries", "logan moore",
     "abella danger", "adriana chechik", "aimi yoshikawa", "amarna miller",
     "angela white", "anna polina", "anri okita", "arabelle raphael",
     "honey_sunshine", "ariana marie", "august ames", "ayu sakurai",
     "belle knox", "bonnie rotten", "brett rossi", "carter cruise",
     "casey calvert", "chanel preston", "charlotte sartre",
     "iori kogawa", "jia lissa", "jessie andrews", "jessie rogers", "lana rhoades",
     "lasirena69", "lauren phillips", "lizz tayler", "maitland ward",
     "mia khalifa", "mia magma", "mia malkova", "nadia ali", "rebecca more",
     "remy lacroix", "renee gracie", "reya sunshine", "rika hoshimi",
     "riley reid", "saki hatsumi", "samantha bentley", "sara tommasi",
     "tasha reign", "tsusaka aoi", "valentina nappi",
     "brendon miller", "griffin barrows", "jordi el nino polla",
     "matthew camp", "rocco steele", "ty mitchell", "amouranth", "belle delphine",
     "cara cunningham", "nang mwe san", "projekt melody",
     
     # Dutch Porn Websites
     "kinky.nl", "geilevrouwen.nl", "sexfilms.nl",
     "echtneuken.nl", "viva.nl", "sexjobs.nl", "vagina.nl", "binkdate.nl", "chatgirl.nl",
 
     # Gay Porn Websites
     "www.men.com", "gaytube.com", "justusboys.com", "gaymaletube.com", "dudetube.com",
     "nextdoorstudios.com", "cockyboys.com", "helixstudios.net", "hothouse.com", "corbinfisher.com",
 
     # Lesbian Porn Websites
     "girlsway.com", "naughtylady.com", "bellesa.co", "sweetsinner.com", "transangelsnetwork.com",
     "girlfriendsfilms.com", "thelesbianexperience.com", "wifelovers.com", "wearehairy.com", "lucasentertainment.com",
 
     # Trans Porn Websites
     "shemale.xxx", "groobygirls.com", "ts-dating.com", "tgirls.com", "trannytube.tv",
     "trans500.com", "pure-ts.com", "transangels.com"
]    


EXPLICIT_REGEX = re.compile("|".join(re.escape(k.lower()) for k in EXPLICIT_KEYWORDS))


def filter_explicit_content(df, columns_to_check):
    """Drops rows where any of the given columns contains an explicit keyword.

    The index is reset because the consent form addresses rows by position,
    so a gapped index renders as empty rows in the table shown to the
    participant.
    """
    if df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns_to_check:
        remaining = ~mask  # only scan rows not already matched
        if not remaining.any():
            break
        mask.loc[remaining] = (
            df.loc[remaining, col]
            .astype("string")
            .str.lower()
            .str.contains(EXPLICIT_REGEX, na=False)
            .fillna(False)
            .astype(bool)
        )
    return df[~mask].reset_index(drop=True)


def redact_emails(df, columns_to_redact):
    """Replaces email addresses in the given columns with ``[email]``.

    Uses the shared ``EMAIL_PATTERN`` so that all platforms agree on what an
    address looks like. Columns that a table does not have are skipped, and
    missing values are left untouched.
    """
    for col in columns_to_redact:
        if col not in df.columns:
            continue
        df[col] = (
            df[col]
            .astype("string")
            .str.replace(eh.EMAIL_PATTERN, "[email]", regex=True)
        )
    return df


# ---------------------------------------------------------------------------


def apply_study_redaction(result: ExtractionResult) -> ExtractionResult:
    """Apply the study's redaction to every table of an extraction result.

    Explicit-content rows are dropped first (only for the tables in
    ``EXPLICIT_FILTERED_TABLES``; a filtered table missing a scanned column
    raises rather than passing through), then addresses are redacted in the
    ``Title``/``Details`` columns of every table. A table with no rows left is
    dropped from the result. Table order and the error counter are preserved.
    """
    kept = []
    for table in result.tables:
        df = table.data_frame
        if not isinstance(df, pd.DataFrame):
            kept.append(table)
            continue
        if table.id in EXPLICIT_FILTERED_TABLES:
            missing = [col for col in EXPLICIT_COLUMNS if col not in df.columns]
            if missing:
                # A filtered table without the columns the filter scans must not
                # slip through unfiltered: fail closed, into the error flow.
                raise ValueError(f"{table.id} lacks {missing}; explicit-content filter cannot run")
            df = filter_explicit_content(df, EXPLICIT_COLUMNS)
        df = redact_emails(df, EMAIL_COLUMNS)
        if df.empty:
            continue
        table.data_frame = df
        kept.append(table)
    return ExtractionResult(tables=kept, errors=result.errors)
