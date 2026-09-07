import type { Host } from "./host";
import type { Export } from "./archive";
import { ArchiveError } from "./archive";
import type { Extraction } from "./extract";
import { ReviewState } from "./review/state";
import { serializePayload, DECLINE_PAYLOAD } from "./payload";
import type { Screens, ScreenHandlers, ErrorKind } from "./review/screens";

export const EXIT = {
  completed: [0, "completed"] as [number, string],
  error: [1, "error"] as [number, string],
  donationFailed: [3, "donation_failed"] as [number, string],
  uploadRejected: [4, "upload_rejected"] as [number, string],
};

export interface ControllerDeps {
  host: Host;
  screens: Screens;
  loadExport(file: File): Promise<Export>;
  runExtraction(exp: Export): Promise<Extraction>;
  sessionId: string;
  appVersion: string;
  userAgent: string;
  now(): string;
  yieldToUi(): Promise<void>;
}

type Phase = "intro" | "working" | "retry" | "tables" | "confirm" | "sending" | "done" | "failed" | "error" | "incomplete";

export class Controller {
  handlers: ScreenHandlers;
  private d: ControllerDeps;
  private phase: Phase = "intro";
  private state: ReviewState | null = null;
  private payload: string | null = null;
  private declined = false;
  private errorKind: ErrorKind = "unexpected";
  private exitCodeOnStop: [number, string] = EXIT.uploadRejected;
  private finished = false;

  constructor(deps: ControllerDeps) {
    this.d = deps;
    this.handlers = {
      onFile: (f) => this.onFile(f),
      // scrollTop (the true here) brings the top of the tables screen back
      // into view: a table switch or a page change moves the participant to
      // content they have not seen, a selection or search change does not.
      onSelectTable: (i) => this.withState((s) => { s.activeIndex = i; this.showTables(true); }),
      onQuery: (i, q) => this.withState((s) => { s.setQuery(i, q); this.showTables(); }),
      onToggleSelect: (i, row) => this.withState((s) => { s.toggleSelected(i, row); this.showTables(); }),
      // The header tick box: all on, or all off, over whatever is visible now
      // (the search result when there is one). Same rule as the desktop's.
      onToggleSelectAll: (i) => this.withState((s) => {
        if (s.allVisibleSelected(i)) s.clearSelection(i); else s.selectAllVisible(i);
        this.showTables();
      }),
      onDeleteSelected: (i) => this.withState((s) => { s.deleteSelected(i); this.showTables(); }),
      onPage: (i, page) => this.withState((s) => { s.setPage(i, page); this.showTables(true); }),
      onUndo: (i) => this.withState((s) => { s.undo(i); this.showTables(); }),
      onProceed: () => this.withState((s) => { this.phase = "confirm"; this.d.screens.confirm(s); }),
      onBack: () => this.withState(() => this.showTables()),
      onDonate: () => this.donate(false),
      onDecline: () => this.donate(true),
      onRetryDonate: () => this.send(),
      onStop: () => this.finishIncomplete(this.exitCodeOnStop),
      onReport: () => this.report(true),
      onSkipReport: () => this.report(false),
    };
  }

  start(): void {
    this.phase = "intro";
    this.d.screens.intro();
  }

  private withState(fn: (s: ReviewState) => void): void {
    if (this.state) fn(this.state);
  }

  private showTables(scrollTop = false): void {
    if (!this.state) return;
    this.phase = "tables";
    this.d.screens.tables(this.state, scrollTop);
  }

  private onFile(file: File): void {
    this.d.host.log("file_selected");
    this.phase = "working";
    this.d.screens.working();
    this.d.loadExport(file).then((exp) => {
      this.d.host.log("archive_read");
      return this.d.yieldToUi().then(() => exp);
    }).then((exp) => this.d.runExtraction(exp)).then((result) => {
      if (result.tables.length === 0) throw new Error("extract_failed");
      this.d.host.log("extracted");
      this.state = new ReviewState(result.tables);
      this.d.host.log("review_shown");
      this.showTables();
    }).catch((err: unknown) => {
      if (err instanceof ArchiveError) {
        this.phase = "retry";
        this.exitCodeOnStop = EXIT.uploadRejected;
        this.d.screens.retry(err.kind);
        return;
      }
      this.fail(err instanceof Error && err.message === "extract_failed" ? "extract_failed" : "unexpected");
    });
  }

  private fail(kind: ErrorKind): void {
    this.errorKind = kind;
    this.phase = "error";
    this.d.host.log("error_shown");
    this.d.screens.error(kind);
  }

  private donate(decline: boolean): void {
    if (!this.state) return;
    this.declined = decline;
    this.d.host.log(decline ? "consent_declined" : "consent_accepted");
    this.payload = decline ? DECLINE_PAYLOAD : serializePayload(this.state);
    this.send();
  }

  private send(): void {
    if (this.payload === null) return;
    this.phase = "sending";
    this.d.screens.sending();
    this.d.host.log("donate_started");
    this.d.host.donate(this.d.sessionId + "-tiktok", this.payload).then((r) => {
      if (r.ok) {
        this.d.host.log("donate_succeeded");
        this.payload = null;
        this.state = null;
        this.phase = "done";
        // Exit before drawing: the donation is delivered, so a throw while
        // rendering the thank-you screen must not turn it into exit 1.
        this.exit(EXIT.completed);
        this.d.screens.done(this.declined);
      } else {
        this.d.host.log("donate_failed");
        if (this.declined) {
          // A failed decline record is invisible infrastructure, as on desktop.
          this.phase = "done";
          this.exit(EXIT.completed);
          this.d.screens.done(true);
          return;
        }
        this.phase = "failed";
        this.exitCodeOnStop = EXIT.donationFailed;
        this.d.screens.failed();
      }
    }).catch(() => this.onUnhandled());
  }

  private report(send: boolean): void {
    if (this.finished || this.phase === "sending") return;
    if (!send) {
      this.d.host.log("error_report_skipped");
      this.finishIncomplete(EXIT.error);
      return;
    }
    this.phase = "sending";
    this.d.screens.sending();
    const body = JSON.stringify({ platform: "tiktok", category: this.errorKind, appVersion: this.d.appVersion, userAgent: this.d.userAgent, timestamp: this.d.now() });
    this.d.host.donate("error-report", body).then(() => {
      this.d.host.log("error_report_sent");
      this.finishIncomplete(EXIT.error);
    }).catch(() => this.onUnhandled());
  }

  // Last-resort handler for anything that escapes the normal control flow
  // (an exception thrown while rendering a screen, surfaced back here via
  // window.onerror, window.onunhandledrejection, or the .catch on the async
  // chains above). Never surfaces exception text: it only ever drives the fixed
  // "unexpected" error screen or, failing that, the same idempotent
  // exit(1, "error") every other ending goes through.
  onUnhandled(): void {
    if (this.finished) return;
    try {
      this.fail("unexpected");
    } catch (_) {
      try {
        this.finishIncomplete(EXIT.error);
      } catch (_) {
        // exit() is idempotent and logs "exited", so the host sees the same
        // ending here as on any other path; if it throws too, nothing is left.
        try {
          this.exit(EXIT.error);
        } catch (_) {
          // deliberately swallowed
        }
      }
    }
  }

  private finishIncomplete(code: [number, string]): void {
    this.phase = "incomplete";
    this.state = null;
    this.payload = null;
    this.d.screens.incomplete();
    this.exit(code);
  }

  private exit(code: [number, string]): void {
    if (this.finished) return;
    this.finished = true;
    this.d.host.log("exited");
    this.d.host.exit(code[0], code[1]);
  }
}
