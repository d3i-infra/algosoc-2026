// jsdom's TextEncoder (backed by Node's util.TextEncoder) returns Uint8Array
// instances from a different realm than globalThis.Uint8Array inside the
// jsdom test environment. fflate relies on `instanceof Uint8Array` to tell
// zip entries apart from plain objects, so under jsdom that check silently
// fails and corrupts archive test fixtures. Rewrap the output in this
// realm's Uint8Array before any test module imports fflate.
const RealTextEncoder = globalThis.TextEncoder;
class RealmSafeTextEncoder extends RealTextEncoder {
  encode(input?: string): Uint8Array {
    return Uint8Array.from(super.encode(input));
  }
}
(globalThis as unknown as { TextEncoder: typeof TextEncoder }).TextEncoder = RealmSafeTextEncoder;
