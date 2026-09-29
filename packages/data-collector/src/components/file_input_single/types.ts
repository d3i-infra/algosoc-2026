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
}
