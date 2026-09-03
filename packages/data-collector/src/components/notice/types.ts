// Matching feldspar's Text/Translatable (duplicated like retry_prompt/types.ts
// to keep this component self-contained — feldspar doesn't export these types).
export interface Translatable {
  translations: { [locale: string]: string }
}
export type Text = Translatable | string

export interface PropsUIPromptNotice {
  __type__: 'PropsUIPromptNotice'
  text: Text
}

export function isPropsUIPromptNotice (body: unknown): body is PropsUIPromptNotice {
  return typeof body === 'object' && body !== null &&
    (body as { __type__?: unknown }).__type__ === 'PropsUIPromptNotice'
}
