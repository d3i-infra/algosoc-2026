import * as React from 'react'
import {
  ReactFactoryContext,
  PrimaryButton,
  BodyLarge,
  BodySmall
} from "@eyra/feldspar"
import TextBundle from "@eyra/feldspar"
import { resolveText } from "../../locale/text"
import { partitionAccepted } from "../../file_drop/accept"
import {
  buildNotices,
  extraFilesNotice,
  folderNotice,
  rejectedNotice
} from "../../file_drop/copy"
import { useFileDrop } from "../../file_drop/use_file_drop"
import { LoadingNotice } from "../loading_notice/loading_notice"
import { pickSingle } from "./select"
import { PropsUIPromptFileInputSingle, Translatable } from "./types"

type Props = PropsUIPromptFileInputSingle & ReactFactoryContext

// The D3I counterpart of feldspar's FileInput: the same panel, note and
// buttons, plus a drop zone and an on-the-spot file type check. It resolves
// the same PayloadFile, so nothing downstream can tell the two apart.
export const FileInputSingle = (props: Props): React.JSX.Element => {
  const [waiting, setWaiting] = React.useState<boolean>(false)
  const [selectedFile, setSelectedFile] = React.useState<File>()
  const [notices, setNotices] = React.useState<string[]>([])
  const input = React.useRef<HTMLInputElement>(null)

  const { resolve, locale } = props
  const { description, note, placeholder, extensions, selectButton, continueButton } = prepareCopy(props)

  function handleClick (): void {
    input.current?.click()
  }

  // The one way to the selected file, for the picker and for a drop alike. The
  // type check runs for picker selections too: a participant can switch the
  // operating system's dialog to "All files".
  function intake (incoming: File[], folders: string[]): void {
    const { accepted, rejected } = partitionAccepted(incoming, extensions)
    const { file, extra } = pickSingle(selectedFile, accepted)
    setSelectedFile(file)
    setNotices(buildNotices([
      [rejectedNotice(), rejected],
      [folderNotice(), folders],
      [extraFilesNotice(), extra]
    ], locale))
  }

  function handleSelect (event: React.ChangeEvent<HTMLInputElement>): void {
    const files = event.target.files
    if (files != null && files.length > 0) {
      intake(Array.from(files), [])
    } else {
      console.log('[FileInput] Error selecting file: ' + JSON.stringify(files))
    }
    // Reset the native input's value so that picking the same file again
    // still fires a change event.
    event.target.value = ""
  }

  function handleConfirm (): void {
    if (selectedFile !== undefined && !waiting) {
      setWaiting(true)
      resolve?.({ __type__: 'PayloadFile', value: selectedFile })
    }
  }

  const { active, zoneProps } = useFileDrop(
    (drop) => intake(drop.files, drop.folders),
    !waiting
  )

  return (
    <>
      <div id='select-panel'>
        <div className='flex-wrap text-bodylarge font-body text-grey1 text-left'>
          {description}
        </div>
        <div className='mt-8' />
        <div
          id='drop-zone'
          {...zoneProps}
          className={`p-6 border-2 rounded ${active ? 'border-primary bg-primarylight' : 'border-grey4'}`}
        >
          <input ref={input} id='input' type='file' className='hidden' accept={extensions} onChange={handleSelect} />
          <div className='flex flex-col sm:flex-row gap-2 sm:gap-4 sm:items-center'>
            <BodyLarge text={selectedFile?.name ?? placeholder} margin='' color={selectedFile === undefined ? 'text-grey2' : 'text-grey1'} />
            <div className='grow' />
            <div className='flex-wrap'>
              <div className='flex flex-row'>
                <PrimaryButton onClick={handleClick} label={selectButton} color='bg-tertiary text-grey1' />
              </div>
            </div>
          </div>
        </div>
        {notices.map((notice) => (
          <React.Fragment key={notice}>
            <div className='mt-2' />
            <BodySmall text={notice} margin='' />
          </React.Fragment>
        ))}
        <div className='mt-4' />
        <div className={`${selectedFile === undefined ? 'opacity-30' : 'opacity-100'}`}>
          <BodySmall text={note} margin='' />
          <div className='mt-8' />
          <div className='flex flex-row gap-4 items-center'>
            <PrimaryButton label={continueButton} onClick={handleConfirm} enabled={selectedFile !== undefined} spinning={waiting} />
            {waiting && <LoadingNotice locale={locale} />}
          </div>
        </div>
      </div>
    </>
  )
}

interface Copy {
  description: string
  note: string
  placeholder: string
  extensions: string
  selectButton: string
  continueButton: string
}

function prepareCopy ({ description, extensions, locale }: Props): Copy {
  return {
    description: resolveText(description, locale),
    note: resolveText(note(), locale),
    placeholder: resolveText(placeholder(), locale),
    extensions: extensions,
    selectButton: resolveText(selectButtonLabel(), locale),
    continueButton: resolveText(continueButtonLabel(), locale)
  }
}

// The four bundles below repeat feldspar's file_input.tsx word for word, for
// the five locales this fork supports, so participants read what they read
// before this prompt replaced feldspar's.

const continueButtonLabel = (): Translatable => {
  return new TextBundle()
    .add('en', 'Continue')
    .add('de', 'Weiter')
    .add('nl', 'Verder')
    .add('it', 'Continua')
    .add('es', 'Continuar')
}

const selectButtonLabel = (): Translatable => {
  return new TextBundle()
    .add('en', 'Choose file')
    .add('de', 'Datei auswählen')
    .add('nl', 'Kies bestand')
    .add('it', 'Scegli file')
    .add('es', 'Elegir archivo')
}

const note = (): Translatable => {
  return new TextBundle()
    .add('en', 'The process to extract the correct data from the file happens on your own device. No data is stored or sent yet.')
    .add('de', 'Der Prozess zum Extrahieren der richtigen Daten aus der Datei erfolgt auf Ihrem eigenen Gerät. Es werden noch keine Daten gespeichert oder gesendet.')
    .add('nl', 'Het proces om de juiste gegevens uit het bestand te halen gebeurt op je eigen apparaat. Er worden nog geen gegevens opgeslagen of verzonden.')
    .add('it', 'Il processo per estrarre i dati corretti dal file avviene sul tuo dispositivo. Nessun dato viene ancora memorizzato o inviato.')
    .add('es', 'El proceso para extraer los datos correctos del archivo ocurre en su propio dispositivo. Aún no se almacenan ni envían datos.')
}

const placeholder = (): Translatable => {
  return new TextBundle()
    .add('en', 'E.g. data.zip')
    .add('de', 'Z.B. data.zip')
    .add('nl', 'Voorbeeld: data.zip')
    .add('it', 'Esempio: data.zip')
    .add('es', 'Ejemplo: data.zip')
}
