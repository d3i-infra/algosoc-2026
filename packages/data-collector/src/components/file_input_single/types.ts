// Matching feldspar's Translatable, duplicated like file_input_multiple/types.ts
// because it is not part of @eyra/feldspar's public export surface.
export interface Translatable {
  translations: { [locale: string]: string }
}

export interface PropsUIPromptFileInputSingle {
  __type__: "PropsUIPromptFileInputSingle"
  // Always an object: the Python side (packages/python/port/api/d3i_props.py)
  // types description as props.Translatable and always calls .toDict() on it.
  description: Translatable
  // An HTML accept string of MIME types, e.g. "application/zip".
  extensions: string
  // Present only when the Python side (packages/python/port/api/d3i_props.py)
  // set it: toDict() omits the key otherwise, and then the component shows its
  // own built-in text. The single-file study platforms (Instagram, Facebook,
  // TikTok) and e2etest set it; every other single-file flow, the example
  // platform included, relies on that fallback.
  example?: Translatable
}
