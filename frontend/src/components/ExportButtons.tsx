import { api } from '../api'

export default function ExportButtons({ experimentId }: { experimentId: string }) {
  return (
    <div className="field-row">
      <a className="btn btn-secondary" href={api.exportUrl(experimentId, 'json')} target="_blank" rel="noreferrer">
        Export JSON
      </a>
      <a className="btn btn-secondary" href={api.exportUrl(experimentId, 'md')} target="_blank" rel="noreferrer">
        Export Markdown
      </a>
    </div>
  )
}
