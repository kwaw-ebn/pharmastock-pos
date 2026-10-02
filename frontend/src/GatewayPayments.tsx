import { useEffect, useState } from "react";
import { api } from "./api";
export default function GatewayPayments({
  notify,
  complete,
  refresh,
}: {
  notify: Function;
  complete: Function;
  refresh: number;
}) {
  const [items, setItems] = useState<any[]>([]),
    [busy, setBusy] = useState("");
  const load = () =>
    api("/payments/pending")
      .then(setItems)
      .catch((e) => notify(e.message, true));
  useEffect(() => {
    load();
  }, [refresh]);
  async function verify(reference: string) {
    setBusy(reference);
    try {
      const r = await api(
        "/payments/" + encodeURIComponent(reference) + "/verify",
        "POST",
      );
      if (r.sale.status === "completed") {
        complete(r.sale);
        notify("Payment verified. The paid receipt is ready.");
      } else
        notify(
          r.sale.status === "paid_review"
            ? "Payment received but stock requires administrator review. Do not dispense."
            : "Payment status: " +
                r.provider_status +
                ". Stock remains reserved unless the provider confirms failure.",
        );
      load();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy("");
    }
  }
  if (!items.length) return null;
  return (
    <section className="panel padded">
      <h2>Pending gateway payments</h2>
      <p className="muted-text">
        Verify payment before dispensing. Closing checkout does not cancel a
        payment or release reserved stock.
      </p>
      {items.map((p) => (
        <div className="toolbar" key={p.reference}>
          <span>
            {p.reference} · GHS {p.total.toFixed(2)} · {p.status}
          </span>
          {p.authorization_url && p.status === "pending" && (
            <a
              className="secondary"
              href={p.authorization_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open secure checkout
            </a>
          )}
          <button
            className="primary"
            disabled={!!busy}
            onClick={() => verify(p.reference)}
          >
            {busy === p.reference ? "Verifying…" : "Verify payment"}
          </button>
        </div>
      ))}
    </section>
  );
}
