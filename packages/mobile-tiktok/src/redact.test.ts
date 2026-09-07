import { redactEmails, redactUsername, redactText } from "./redact";

test("emails become the placeholder", () => {
  expect(redactEmails("mail me at a.b-c+d@example.co.uk now")).toBe("mail me at [email] now");
  expect(redactEmails("two x@y.com and z@w.org")).toBe("two [email] and [email]");
  expect(redactEmails("no address here")).toBe("no address here");
});

test("username is replaced whole-token and case-insensitively", () => {
  expect(redactUsername("hi Alice, alice! @alice", "alice")).toBe("hi [user], [user]! @[user]");
  expect(redactUsername("alice", "alice")).toBe("[user]");
  expect(redactUsername("alicex xalice", "alice")).toBe("alicex xalice");
  expect(redactUsername("alice alice", "alice")).toBe("[user] [user]");
  expect(redactUsername("alice_1 alice", "alice")).toBe("alice_1 [user]");
  expect(redactUsername("éalice alice", "alice")).toBe("éalice [user]");
});

test("username with regex metacharacters is escaped", () => {
  expect(redactUsername("call a.b now", "a.b")).toBe("call [user] now");
  expect(redactUsername("call axb now", "a.b")).toBe("call axb now");
});

test("redactText does both, and skips username when null", () => {
  expect(redactText("alice at alice@x.com", "alice")).toBe("[user] at [email]");
  expect(redactText("alice at alice@x.com", null)).toBe("alice at [email]");
  expect(redactText("alice", "")).toBe("alice");
});
