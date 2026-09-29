import * as React from 'react'
import { BodyLarge } from "@eyra/feldspar"
import TextBundle from "@eyra/feldspar"
import { resolveText } from "../../locale/text"

// Shown with a file prompt once the participant has pressed "Continue":
// validation and extraction run in Pyodide on the main page and can take
// minutes on a large archive, and a reload throws that work away.
export const LoadingNotice = ({ locale }: { locale: string }): React.JSX.Element => (
  <BodyLarge text={resolveText(loadingNoticeText(), locale)} margin='' />
)

const loadingNoticeText = () => {
  return new TextBundle()
    .add('en', 'This may take a few minutes. Please be patient and do not reload the page.')
    .add('de', 'Dies kann einige Minuten dauern. Bitte haben Sie etwas Geduld und laden Sie die Seite nicht neu.')
    .add('nl', 'Dit kan enkele minuten duren. Even geduld en laad de pagina niet opnieuw.')
    .add('it', "L'operazione può richiedere alcuni minuti. La preghiamo di attendere e di non ricaricare la pagina.")
    .add('es', 'Esto puede tardar unos minutos. Tenga paciencia y no recargue la página.')
}
