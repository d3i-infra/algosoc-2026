import TextBundle from '@eyra/feldspar'
import { resolveText } from '../locale/text'

export const rejectedNotice = (): TextBundle => {
  return new TextBundle()
    .add('en', 'Not added, because the file type does not match: {names}')
    .add('de', 'Nicht hinzugefügt, da der Dateityp nicht passt: {names}')
    .add('nl', 'Niet toegevoegd, omdat het bestandstype niet klopt: {names}')
    .add('it', 'Non aggiunto, perché il tipo di file non corrisponde: {names}')
    .add('es', 'No añadido, porque el tipo de archivo no coincide: {names}')
}

export const folderNotice = (): TextBundle => {
  return new TextBundle()
    .add('en', 'Folders cannot be added. Please add the file itself: {names}')
    .add('de', 'Ordner können nicht hinzugefügt werden. Bitte fügen Sie die Datei selbst hinzu: {names}')
    .add('nl', 'Mappen kunnen niet worden toegevoegd. Voeg het bestand zelf toe: {names}')
    .add('it', 'Non è possibile aggiungere cartelle. Aggiunga il file stesso: {names}')
    .add('es', 'No se pueden añadir carpetas. Añada el archivo en sí: {names}')
}

export const extraFilesNotice = (): TextBundle => {
  return new TextBundle()
    .add('en', 'Only one file can be added. Not added: {names}')
    .add('de', 'Es kann nur eine Datei hinzugefügt werden. Nicht hinzugefügt: {names}')
    .add('nl', 'Er kan maar één bestand worden toegevoegd. Niet toegevoegd: {names}')
    .add('it', 'È possibile aggiungere un solo file. Non aggiunto: {names}')
    .add('es', 'Solo se puede añadir un archivo. No añadido: {names}')
}

/**
 * One resolved notice per entry that has names, in entry order. `text` is
 * `unknown` for the same reason resolveText takes `unknown`: it is total.
 */
export function buildNotices (
  entries: Array<[text: unknown, names: string[]]>,
  locale: string
): string[] {
  return entries
    .filter(([, names]) => names.length > 0)
    // A replacer function, so a file name containing "$&" is inserted as is.
    .map(([text, names]) => resolveText(text, locale).replace('{names}', () => names.join(', ')))
}
