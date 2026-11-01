import type { IRealtimeClient } from '@/application/ports/repositories';

export class RealtimeClient implements IRealtimeClient {
  private socket: WebSocket | null = null;

  private reconnectAttempts = 0;

  private shouldReconnect = false;

  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private onMessage?: (event: unknown) => void;

  private onStatus?: (status: 'connecting' | 'connected' | 'disconnected') => void;

  private connectInput?: {
    baseUrl: string;
    sessionId: string;
    accessToken: string;
    stationId: string;
  };

  connect(input: {
    baseUrl: string;
    sessionId: string;
    accessToken: string;
    stationId: string;
    onMessage: (event: unknown) => void;
    onStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  }): void {
    this.shouldReconnect = true;
    this.onMessage = input.onMessage;
    this.onStatus = input.onStatus;
    this.connectInput = {
      baseUrl: input.baseUrl,
      sessionId: input.sessionId,
      accessToken: input.accessToken,
      stationId: input.stationId
    };

    this.closeSocket({ emitDisconnected: false, disableReconnect: false });
    this.openSocket();
  }

  disconnect(): void {
    this.closeSocket({ emitDisconnected: true, disableReconnect: true });
  }

  sendEvent(type: string, payload: Record<string, unknown>): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type, payload }));
    }
  }

  sendPong(payload: Record<string, unknown>): void {
    this.sendEvent('pong', payload);
  }

  private openSocket() {
    if (!this.connectInput) {
      return;
    }
    if (this.socket && (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)) {
      return;
    }
    this.clearReconnectTimer();

    const wsUrl = this.connectInput.baseUrl
      .replace(/^http:\/\//, 'ws://')
      .replace(/^https:\/\//, 'wss://');

    this.onStatus?.('connecting');
    const socket = new WebSocket(
      `${wsUrl}/ws?sessionId=${encodeURIComponent(this.connectInput.sessionId)}&stationId=${encodeURIComponent(this.connectInput.stationId)}&token=${encodeURIComponent(this.connectInput.accessToken)}`
    );
    this.socket = socket;

    socket.onopen = () => {
      if (this.socket !== socket) {
        return;
      }
      this.reconnectAttempts = 0;
      this.onStatus?.('connected');
    };

    socket.onmessage = (event) => {
      if (this.socket !== socket) {
        return;
      }
      try {
        const parsed = JSON.parse(String(event.data));
        this.onMessage?.(parsed);
      } catch {
        this.onMessage?.(event.data);
      }
    };

    socket.onerror = () => undefined;

    socket.onclose = () => {
      if (this.socket !== socket) {
        return;
      }
      this.socket = null;
      if (!this.shouldReconnect) {
        this.onStatus?.('disconnected');
        return;
      }

      this.onStatus?.('connecting');
      const wait = Math.min(30000, 800 * 2 ** this.reconnectAttempts + Math.floor(Math.random() * 500));
      this.reconnectAttempts += 1;
      this.reconnectTimer = setTimeout(() => this.openSocket(), wait);
    };
  }

  private closeSocket(input: { emitDisconnected: boolean; disableReconnect: boolean }) {
    if (input.disableReconnect) {
      this.shouldReconnect = false;
    }
    this.clearReconnectTimer();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      try {
        socket.close();
      } catch {
        // noop
      }
    }
    if (input.emitDisconnected) {
      this.onStatus?.('disconnected');
    }
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
