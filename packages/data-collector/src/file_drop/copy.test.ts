import { Translator } from '@eyra/feldspar'
import { DEFAULT_UI_LOCALE } from '../locale/policy'
import {
  buildNotices,
  rejectedNotice,
  folderNotice,
  extraFilesNotice
} from './copy'
import * as copy from './copy'

// Mirror the fork's real wiring (App.tsx -> ScriptHostComponent) so this test
// sees the same fallback chain as the running app (ADR-0037).
beforeAll(() => {
  Translator.setDefaultLocale(DEFAULT_UI_LOCALE)
})

const LOCALES = ['de', 'en', 'es', 'it', 'nl']

describe('copy bundles', () => {
  const bundles = { rejectedNotice, folderNotice, extraFilesNotice }

  it.each(Object.entries(bundles))('%s covers exactly the five UI locales', (_name, bundle) => {
    expect(Object.keys(bundle().translations).sort()).toEqual(LOCALES)
  })

  it.each([rejectedNotice, folderNotice, extraFilesNotice])(
    'notice %# carries the {names} placeholder in every locale',
    (bundle) => {
      for (const text of Object.values(bundle().translations)) {
        expect(text).toContain('{names}')
      }
    }
  )

  it('exports no copy that announces drag and drop', () => {
    expect(Object.keys(copy).sort()).toEqual(
      ['buildNotices', 'extraFilesNotice', 'folderNotice', 'rejectedNotice']
    )
  })
})

describe('buildNotices', () => {
  it('returns nothing when no entry has names', () => {
    expect(buildNotices([[rejectedNotice(), []], [folderNotice(), []]], 'en')).toEqual([])
  })

  it('fills in the names, comma separated, in the requested locale', () => {
    expect(buildNotices([[rejectedNotice(), ['a.pdf', 'b.docx']]], 'en')).toEqual([
      'Not added, because the file type does not match: a.pdf, b.docx'
    ])
    expect(buildNotices([[rejectedNotice(), ['a.pdf']]], 'nl')).toEqual([
      'Niet toegevoegd, omdat het bestandstype niet klopt: a.pdf'
    ])
  })

  it('keeps entry order and skips empty entries', () => {
    const notices = buildNotices(
      [[rejectedNotice(), ['a.pdf']], [extraFilesNotice(), []], [folderNotice(), ['takeout']]],
      'en'
    )
    expect(notices).toEqual([
      'Not added, because the file type does not match: a.pdf',
      'Folders cannot be added. Please add the file itself: takeout'
    ])
  })

  it('does not treat a file name as a replacement pattern', () => {
    expect(buildNotices([[rejectedNotice(), ['$&.pdf']]], 'en')).toEqual([
      'Not added, because the file type does not match: $&.pdf'
    ])
  })
})
