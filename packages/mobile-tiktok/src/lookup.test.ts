import { get, getFirst, itemGet, cellText } from "./lookup";

const data = { "Your Activity": { "Watch History": { VideoList: [{ Date: "d", Link: "l" }] } }, Comment: { Comments: { CommentsList: [] } } };

test("get walks alternatives per level", () => {
  expect(get(data, ["Activity", "Your Activity"], ["Video Browsing History", "Watch History"], "VideoList")).toEqual([{ Date: "d", Link: "l" }]);
  expect(get(data, "Activity", "Watch History")).toBeUndefined();
  expect(get(data, ["Nope", "Nah"], "x")).toBeUndefined();
  expect(get("not an object", "a")).toBeUndefined();
});

test("getFirst returns the first defined path", () => {
  expect(getFirst(data, [["Activity", "Your Activity"], "Watch History", "VideoList"], ["Likes and Favorites", "Like List", "ItemFavoriteList"])).toHaveLength(1);
  expect(getFirst(data, ["Missing"], ["Also", "Missing"])).toBeUndefined();
});

test("itemGet tries each key then its lowercase form and defaults to empty string", () => {
  expect(itemGet({ Date: "x" }, "Date")).toBe("x");
  expect(itemGet({ username: "u" }, "UserName", "User Name")).toBe("u");
  expect(itemGet({ Date: null }, "Date")).toBeNull();
  expect(itemGet({}, "Link")).toBe("");
});

test("itemGet throws for a non-object item, as Python's .get would", () => {
  expect(() => itemGet("string", "Date")).toThrow();
  expect(() => itemGet(null, "Date")).toThrow();
});

test("cellText matches String(JSON.parse(df.to_json())) semantics", () => {
  expect(cellText("a")).toBe("a");
  expect(cellText(5)).toBe("5");
  expect(cellText(5.0)).toBe("5");
  expect(cellText(null)).toBe("null");
  expect(cellText(undefined)).toBe("null");
  expect(cellText(true)).toBe("true");
  expect(cellText(["a", "b"])).toBe("a,b");
  expect(cellText(Number("7432323587161328929"))).toBe(String(Number("7432323587161328929")));
});
