import { useCallback, useEffect, useRef, useState } from 'react'

import { apiClient } from '@core/lib/api-client'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Input } from '@core/components/ui/input'
import { Label } from '@core/components/ui/label'
import { toast } from '@core/components/ui/toast'
import type { StatsGroup } from '@stats/types'

interface ImportStatus {
  job_id: string
  status: 'running' | 'done' | 'error'
  inserted: number
  skipped: number
  events: number
  processed: number
  total: number
  error: string | null
}

function DropZone({
  onFile,
  disabled,
}: {
  onFile: (f: File) => void
  disabled: boolean
}) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handle = useCallback(
    (f: File | null | undefined) => {
      if (!f) return
      if (!f.name.endsWith('.json')) {
        toast.error('File must be a .json export')
        return
      }
      onFile(f)
    },
    [onFile],
  )

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handle(e.dataTransfer.files[0])
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={[
        'flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed p-4 text-center transition-colors',
        dragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50',
        disabled ? 'pointer-events-none opacity-50' : '',
      ].join(' ')}
    >
      <span className="text-2xl">📂</span>
      <p className="text-sm font-medium">Drop result.json or click to browse</p>
      <input
        ref={inputRef}
        type="file"
        accept=".json"
        className="hidden"
        onChange={(e) => handle(e.target.files?.[0])}
      />
    </div>
  )
}

function StatusCard({ status }: { status: ImportStatus }) {
  const isRunning = status.status === 'running'
  const isError = status.status === 'error'
  const isDone = status.status === 'done'

  return (
    <div
      className={[
        'rounded-lg border p-4 text-sm',
        isDone ? 'border-green-500/40 bg-green-500/5' : '',
        isError ? 'border-destructive/40 bg-destructive/5' : '',
        isRunning ? 'border-border bg-muted/30' : '',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 font-medium">
        {isRunning && <span className="animate-spin inline-block">⏳</span>}
        {isDone && <span>✅</span>}
        {isError && <span>❌</span>}
        <span>
          {isRunning ? 'Importing...' : isDone ? 'Import complete' : 'Import failed'}
        </span>
      </div>

      {isRunning && status.total > 0 && (
        <div className="mt-3 space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{status.processed.toLocaleString()} / {status.total.toLocaleString()} messages</span>
            <span>{Math.round((status.processed / status.total) * 100)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${Math.round((status.processed / status.total) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {isRunning && status.total === 0 && (
        <p className="mt-2 text-xs text-muted-foreground">Parsing JSON file...</p>
      )}

      {isDone && (
        <div className="mt-2 grid grid-cols-3 gap-2 text-center">
          <div className="rounded bg-muted/50 p-2">
            <div className="text-lg font-bold">{status.inserted.toLocaleString()}</div>
            <div className="text-xs text-muted-foreground">Inserted</div>
          </div>
          <div className="rounded bg-muted/50 p-2">
            <div className="text-lg font-bold">{status.skipped.toLocaleString()}</div>
            <div className="text-xs text-muted-foreground">Skipped</div>
          </div>
          <div className="rounded bg-muted/50 p-2">
            <div className="text-lg font-bold">{status.events.toLocaleString()}</div>
            <div className="text-xs text-muted-foreground">Events</div>
          </div>
        </div>
      )}

      {isError && (
        <p className="mt-2 text-destructive text-xs font-mono break-all">{status.error}</p>
      )}
    </div>
  )
}

type ImportMode = 'upload' | 'path'

export default function ImportPage() {
  const [groups, setGroups] = useState<StatsGroup[]>([])
  const [chatId, setChatId] = useState('')
  const [mode, setMode] = useState<ImportMode>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [serverPath, setServerPath] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [jobStatus, setJobStatus] = useState<ImportStatus | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    apiClient
      .get<StatsGroup[]>('/stats/groups')
      .then((r) => {
        setGroups(r.data)
        if (r.data.length === 1) setChatId(String(r.data[0].chat_id))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const startPolling = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const r = await apiClient.get<ImportStatus>(`/stats/import/${jobId}`)
        setJobStatus(r.data)
        if (r.data.status !== 'running') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          setSubmitting(false)
        }
      } catch (err) {
        console.error('Import poll failed:', err)
        clearInterval(pollRef.current!)
        pollRef.current = null
        setSubmitting(false)
      }
    }, 1500)
  }

  const handleUpload = async () => {
    if (!file) { toast.error('Select a file first'); return }
    if (!chatId || chatId === '__custom') { toast.error('Select a group'); return }

    const form = new FormData()
    form.append('file', file)

    setSubmitting(true)
    setUploadPct(0)
    setJobStatus(null)

    try {
      const r = await apiClient.post<ImportStatus>(
        `/stats/import?chat_id=${chatId}`,
        form,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 600_000,
          onUploadProgress: (e) => {
            if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100))
          },
        },
      )
      setUploadPct(null)
      setJobStatus(r.data)
      if (r.data.status === 'running') {
        startPolling(r.data.job_id)
      } else {
        setSubmitting(false)
      }
    } catch (err) {
      setUploadPct(null)
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Upload failed. For large files use server path instead.')
      setSubmitting(false)
    }
  }

  const handleByPath = async () => {
    if (!serverPath.trim()) { toast.error('Enter a file path'); return }
    if (!chatId || chatId === '__custom') { toast.error('Select a group'); return }

    setSubmitting(true)
    setJobStatus(null)

    try {
      const r = await apiClient.post<ImportStatus>('/stats/import/by-path', {
        path: serverPath.trim(),
        chat_id: Number(chatId),
      })
      setJobStatus(r.data)
      if (r.data.status === 'running') {
        startPolling(r.data.job_id)
      } else {
        setSubmitting(false)
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Failed to start import')
      setSubmitting(false)
    }
  }

  const canSubmit = chatId && chatId !== '__custom' && !submitting && (
    mode === 'upload' ? !!file : !!serverPath.trim()
  )

  return (
    <div className="space-y-5">


      <Card>
        <CardHeader>
          <CardTitle className="text-base">Import Telegram Desktop export</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label>Target group</Label>
            {groups.length > 0 ? (
              <select
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
                disabled={submitting}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Select a group...</option>
                {groups.map((g) => (
                  <option key={g.chat_id} value={String(g.chat_id)}>
                    {g.title} ({g.chat_id})
                  </option>
                ))}
                <option value="__custom">Enter manually...</option>
              </select>
            ) : null}
            {(groups.length === 0 || chatId === '__custom') && (
              <Input
                placeholder="e.g. -1001234567890"
                value={chatId === '__custom' ? '' : chatId}
                onChange={(e) => setChatId(e.target.value)}
                disabled={submitting}
              />
            )}
          </div>

          <div className="space-y-2">
            <Label>Method</Label>
            <div className="flex rounded-md border w-fit">
              <button
                onClick={() => setMode('upload')}
                className={`h-8 px-3 text-xs rounded-l-md transition-colors ${mode === 'upload' ? 'bg-muted font-semibold' : 'hover:bg-muted/50'}`}
                disabled={submitting}
              >
                File upload
              </button>
              <button
                onClick={() => setMode('path')}
                className={`h-8 px-3 text-xs rounded-r-md transition-colors ${mode === 'path' ? 'bg-muted font-semibold' : 'hover:bg-muted/50'}`}
                disabled={submitting}
              >
                Server path
              </button>
            </div>
          </div>

          {mode === 'upload' ? (
            <div className="space-y-1.5">
              <DropZone onFile={setFile} disabled={submitting} />
              {file && (
                <p className="text-xs text-muted-foreground">
                  Selected: <span className="font-medium">{file.name}</span>{' '}
                  ({(file.size / 1024 / 1024).toFixed(1)} MB)
                  {file.size > 100 * 1024 * 1024 && (
                    <span className="ml-1 text-destructive">
                      File over 100 MB - use server path instead
                    </span>
                  )}
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label>Path to result.json inside the container</Label>
              <Input
                placeholder="/tmp/result.json"
                value={serverPath}
                onChange={(e) => setServerPath(e.target.value)}
                disabled={submitting}
              />
              <p className="text-xs text-muted-foreground">
                Copy first:
                <code className="ml-1 text-foreground bg-muted px-1 rounded">
                  docker cp result.json yoink:/tmp/result.json
                </code>
              </p>
            </div>
          )}

          {uploadPct !== null && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Uploading...</span>
                <span>{uploadPct}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-200"
                  style={{ width: `${uploadPct}%` }}
                />
              </div>
            </div>
          )}

          {jobStatus && <StatusCard status={jobStatus} />}

          <Button
            onClick={mode === 'upload' ? handleUpload : handleByPath}
            disabled={!canSubmit}
            className="w-full sm:w-auto"
          >
            {uploadPct !== null
              ? `Uploading ${uploadPct}%...`
              : submitting
                ? 'Importing...'
                : 'Start import'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">How to export chat history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <ol className="list-decimal list-inside space-y-1">
            <li>Open Telegram Desktop</li>
            <li>Go to the group chat you want to import</li>
            <li>Click the three-dot menu - Export chat history</li>
            <li>Uncheck all media, select <strong>Machine-readable JSON</strong></li>
            <li>Click Export and wait for it to finish</li>
            <li>Upload the <code className="text-foreground bg-muted px-1 rounded">result.json</code> above</li>
          </ol>
          <p className="pt-1">
            For files over 100 MB, use the "Server path" method to avoid Cloudflare upload limits.
          </p>
          <p>
            Already-imported messages are skipped automatically - safe to re-import.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
