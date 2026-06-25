type StatusCallback = (status: 'connected' | 'disconnected' | 'reconnecting') => void
type MessageCallback = (data: Record<string, unknown>) => void

export class WebSocketClient {
  private url: string
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  private reconnectDelay = 1000
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private messageCallbacks: MessageCallback[] = []
  private statusCallbacks: StatusCallback[] = []
  private destroyed = false

  constructor(url: string) {
    this.url = url
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return
    this.destroyed = false

    try {
      this.ws = new WebSocket(this.url)
    } catch (e) {
      console.error('[WS] Failed to create WebSocket:', e)
      this.scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      console.log('[WS] Connected')
      this.reconnectAttempts = 0
      this.reconnectDelay = 1000
      this.notifyStatus('connected')
      this.startPing()
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data)
        this.messageCallbacks.forEach((cb) => cb(data))
      } catch {
        // ignore non-JSON messages
      }
    }

    this.ws.onclose = () => {
      console.log('[WS] Disconnected')
      this.stopPing()
      this.notifyStatus('disconnected')
      if (!this.destroyed) {
        this.scheduleReconnect()
      }
    }

    this.ws.onerror = () => {
      console.error('[WS] Error')
    }
  }

  disconnect(): void {
    this.destroyed = true
    this.stopPing()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.notifyStatus('disconnected')
  }

  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  onMessage(callback: MessageCallback): void {
    this.messageCallbacks.push(callback)
  }

  onStatusChange(callback: StatusCallback): void {
    this.statusCallbacks.push(callback)
  }

  private scheduleReconnect(): void {
    if (this.destroyed || this.reconnectAttempts >= this.maxReconnectAttempts) return
    this.reconnectAttempts++
    this.notifyStatus('reconnecting')
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000)
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`)
    setTimeout(() => this.connect(), delay)
  }

  private startPing(): void {
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping' })
    }, 30000)
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  private notifyStatus(status: 'connected' | 'disconnected' | 'reconnecting'): void {
    this.statusCallbacks.forEach((cb) => cb(status))
  }
}
