import crypto from 'node:crypto';
import { AlertDispatcher, AlertMessage } from './dispatchers';

export interface SignedWebhookOptions {
  url: string;
  secret: string;
  timeoutMs?: number;
}

export class SignedWebhookDispatcher implements AlertDispatcher {
  name = 'signed-webhook';

  constructor(private readonly options: SignedWebhookOptions) {}

  async dispatch(message: AlertMessage): Promise<void> {
    const payload = JSON.stringify({
      timestamp: new Date().toISOString(),
      message,
    });

    const signature = crypto.createHmac('sha256', this.options.secret).update(payload).digest('hex');

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 5000);

    try {
      const response = await fetch(this.options.url, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-mekka-signature': signature,
        },
        body: payload,
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Webhook responded with status ${response.status}`);
      }
    } finally {
      clearTimeout(timeout);
    }
  }
}
