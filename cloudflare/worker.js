import { DurableObject } from "cloudflare:workers";

const PORT = 8000;
const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000;

export class CopycatContainer extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.env = env;
    this.starting = undefined;
  }

  async fetch(request) {
    if (!this.env.SUPABASE_URL || !this.env.SUPABASE_SERVICE_ROLE_KEY) {
      return Response.json(
        { detail: "The service is not configured. Set its Supabase secrets in Cloudflare." },
        { status: 503 },
      );
    }

    this.starting ??= this.startAndWaitForPort().finally(() => {
      this.starting = undefined;
    });
    await this.starting;

    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    const forwarded = new Request(url, request);
    forwarded.headers.delete("host");
    return this.ctx.container.getTcpPort(PORT).fetch(forwarded);
  }

  async startAndWaitForPort() {
    const container = this.ctx.container;
    if (!container.running) {
      container.start({
        image: container.images.base,
        instance: "basic",
        enableInternet: true,
        env: {
          PORT: String(PORT),
          SUPABASE_URL: this.env.SUPABASE_URL,
          SUPABASE_SERVICE_ROLE_KEY: this.env.SUPABASE_SERVICE_ROLE_KEY,
        },
      });
    }
    await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);

    const port = container.getTcpPort(PORT);
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await port.fetch("http://container/api/ready", {
          signal: AbortSignal.timeout(1000),
        });
        await response.body?.cancel();
        if (response.ok) return;
      } catch {
        // The container may still be starting; retry its readiness check.
      }
      await scheduler.wait(200);
    }
    throw new Error("CopyCat container did not become ready.");
  }
}

export default {
  fetch(request, env) {
    return env.COPYCAT_CONTAINER.getByName("copycat").fetch(request);
  },
};
