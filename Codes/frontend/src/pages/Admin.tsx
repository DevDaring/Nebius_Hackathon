import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Activity, BarChart3, Cloud, Cpu, FlaskConical, Lock, ServerCog, ToggleLeft } from "lucide-react";
import { ApiError } from "@/api/http";
import { useAdminIntegrations, useCapabilities } from "@/api/hooks";
import type { FeatureFlag } from "@/api/types";
import { ErrorState, PageHeader } from "@/components/ui";
import { formatDateTime, formatInt } from "@/lib/format";
import { useAuth } from "@/store/auth";

function Card({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="card p-5">
      <h2 className="mb-3 flex items-center gap-2 font-bold">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-sm text-ink-3">{k}</dt>
      <dd className="min-w-0 break-words text-sm font-medium">{children}</dd>
    </div>
  );
}

function Status({ ok, label }: { ok: boolean | null; label: string }) {
  const cls = ok === null ? "border-line text-ink-2" : ok ? "border-teal-ink/50 bg-teal/10 text-teal-ink" : "border-coral-ink/40 bg-coral/10 text-coral-ink";
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>{label}</span>;
}

const Mono = ({ children }: { children: ReactNode }) => (
  <span className="font-mono text-[0.8rem]" lang="en" translate="no">
    {children}
  </span>
);

/**
 * Developer / admin integration status: active models, capabilities with reasons, inference health,
 * redacted usage counters, Nebius Cloud auth status, deployment version and evaluation jobs.
 * Read-only: no secrets and no Cloud controls are ever shown here.
 */
export default function AdminPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const user = useAuth((s) => s.user);
  const isAdmin = !!user?.roles?.includes("admin");
  const q = useAdminIntegrations(isAdmin);
  const caps = useCapabilities();
  const when = (iso: string | null | undefined) => (iso ? formatDateTime(iso, lang) : "—");

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <PageHeader title={t("admin.title")} />
        <p className="card flex items-start gap-3 p-5 text-sm">
          <Lock size={18} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
          {t("admin.forbidden")}
        </p>
      </div>
    );
  }

  const d = q.data;
  // Talk is text-based: the speech flag stays in the API for clients, but is not listed as a feature here.
  const features = Object.entries(caps.data?.features ?? {}).filter((e): e is [string, FeatureFlag] => !!e[1] && e[0] !== "speech");
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader title={t("admin.title")} subtitle={t("admin.subtitle")} />
      {q.isLoading && <div className="skeleton h-64" />}
      {q.isError && (
        <ErrorState
          message={q.error instanceof ApiError && q.error.status === 403 ? t("admin.forbidden") : q.error instanceof ApiError && q.error.status === 404 ? t("admin.notAvailable") : t("errors.generic")}
          onRetry={() => void q.refetch()}
        />
      )}
      <div className="grid gap-5 md:grid-cols-2">
        <Card title={t("admin.models")} icon={<Cpu size={17} className="text-marigold-ink" aria-hidden />}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <Row k={t("admin.provider")}>
              <Mono>{caps.data?.inference.provider ?? "—"}</Mono>
            </Row>
            <Row k={t("admin.chatModel")}>
              <Mono>{caps.data?.inference.planner_model ?? "—"} · {caps.data?.inference.chat_model ?? "—"}</Mono>
            </Row>
            <Row k={t("admin.mode")}>
              <Mono>{caps.data?.mode ?? "—"}</Mono>
            </Row>
          </dl>
        </Card>

        <Card title={t("admin.health")} icon={<Activity size={17} className="text-teal-ink" aria-hidden />}>
          {d ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <Row k={t("admin.status")}>
                <Status
                  ok={d.inference_health.ok}
                  label={d.inference_health.ok === null ? t("admin.notChecked") : d.inference_health.ok ? t("admin.ok") : t("admin.notOk")}
                />
              </Row>
              <Row k={t("admin.model")}>
                <Mono>{d.inference_health.model ?? "—"}</Mono>
              </Row>
              <Row k={t("admin.latency")}>{d.inference_health.latency_ms !== null ? t("admin.ms", { n: formatInt(d.inference_health.latency_ms, lang) }) : "—"}</Row>
              <Row k={t("admin.errorCategory")}>
                <Mono>{d.inference_health.error_category ?? "—"}</Mono>
              </Row>
              <Row k={t("admin.checkedAt")}>{when(d.inference_health.checked_at)}</Row>
            </dl>
          ) : (
            <p className="text-sm text-ink-3">—</p>
          )}
        </Card>

        <Card title={t("admin.capabilities")} icon={<ToggleLeft size={17} className="text-marigold-ink" aria-hidden />}>
          {features.length ? (
            <ul className="divide-y divide-line">
              {features.map(([name, f]) => (
                <li key={name} className="flex flex-wrap items-start justify-between gap-2 py-2">
                  <div className="min-w-0">
                    <Mono>{name}</Mono>
                    {f.model && (
                      <p className="text-xs text-ink-3">
                        <Mono>{f.model}</Mono>
                        {f.nvidia === false && <> · {t("admin.nonNvidia")}</>}
                      </p>
                    )}
                    {f.reason && (
                      <p className="text-xs text-ink-3" lang="en">
                        {f.reason}
                      </p>
                    )}
                  </div>
                  <Status ok={f.enabled} label={f.enabled ? t("admin.enabled") : t("admin.disabled")} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-3">{t("admin.noCapabilities")}</p>
          )}
        </Card>

        <Card title={t("admin.usage")} icon={<BarChart3 size={17} className="text-violet-ink" aria-hidden />}>
          {d ? (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
                <Row k={t("admin.since")}>{when(d.usage.since)}</Row>
                <Row k={t("admin.requests")}>{formatInt(d.usage.requests, lang)}</Row>
                <Row k={t("admin.tokens")}>{t("admin.tokensValue", { p: formatInt(d.usage.prompt_tokens, lang), c: formatInt(d.usage.completion_tokens, lang) })}</Row>
                <Row k={t("admin.errors")}>
                  {Object.entries(d.usage.errors ?? {})
                    .map(([k, v]) => `${k} ${formatInt(v, lang)}`)
                    .join(" · ") || "—"}
                </Row>
              </dl>
              {Object.keys(d.usage.by_model ?? {}).length > 0 && (
                <table className="mt-3 w-full text-left text-xs">
                  <caption className="sr-only">{t("admin.byModel")}</caption>
                  <thead className="text-ink-3">
                    <tr>
                      <th scope="col" className="py-1 font-semibold">{t("admin.model")}</th>
                      <th scope="col" className="py-1 font-semibold">{t("admin.requests")}</th>
                      <th scope="col" className="py-1 font-semibold">{t("admin.tokens")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(d.usage.by_model).map(([m, u]) => (
                      <tr key={m} className="border-t border-line">
                        <td className="py-1">
                          <Mono>{m}</Mono>
                        </td>
                        <td className="num py-1">{formatInt(u.requests, lang)}</td>
                        <td className="num py-1">{t("admin.tokensValue", { p: formatInt(u.prompt_tokens, lang), c: formatInt(u.completion_tokens, lang) })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="mt-2 text-xs text-ink-3">{t("admin.redacted")}</p>
            </>
          ) : (
            <p className="text-sm text-ink-3">—</p>
          )}
        </Card>

        <Card title={t("admin.cloud")} icon={<Cloud size={17} className="text-marigold-ink" aria-hidden />}>
          {d ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <Row k={t("admin.authMode")}>
                <Mono>{d.cloud.auth_mode}</Mono>
              </Row>
              <Row k={t("admin.configured")}>{d.cloud.configured ? t("admin.yes") : t("admin.no")}</Row>
              <Row k={t("admin.status")}>
                <Status ok={d.cloud.status === "ok" ? true : d.cloud.status === "not_configured" ? null : false} label={d.cloud.status} />
              </Row>
              {d.cloud.detail && (
                <Row k={t("admin.detail")}>
                  <span lang="en">{d.cloud.detail}</span>
                </Row>
              )}
              <Row k={t("admin.checkedAt")}>{when(d.cloud.checked_at)}</Row>
            </dl>
          ) : (
            <p className="text-sm text-ink-3">—</p>
          )}
          <p className="mt-2 text-xs text-ink-3">{t("admin.noControls")}</p>
        </Card>

        <Card title={t("admin.deployment")} icon={<ServerCog size={17} className="text-ink-3" aria-hidden />}>
          {d ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <Row k={t("admin.version")}>
                <Mono>{d.deployment.version ?? "—"}</Mono>
              </Row>
              <Row k={t("admin.commit")}>
                <Mono>{d.deployment.git_commit ?? "—"}</Mono>
              </Row>
              <Row k={t("admin.environment")}>
                <Mono>{d.deployment.environment ?? "—"}</Mono>
              </Row>
            </dl>
          ) : (
            <p className="text-sm text-ink-3">—</p>
          )}
        </Card>

        <div className="md:col-span-2">
          <Card title={t("admin.evaluation")} icon={<FlaskConical size={17} className="text-violet-ink" aria-hidden />}>
            {d && d.evaluation_jobs.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[32rem] text-left text-sm">
                  <thead className="text-xs text-ink-3">
                    <tr>
                      <th scope="col" className="py-1.5 font-semibold">{t("admin.job")}</th>
                      <th scope="col" className="py-1.5 font-semibold">{t("admin.status")}</th>
                      <th scope="col" className="py-1.5 font-semibold">{t("admin.report")}</th>
                      <th scope="col" className="py-1.5 font-semibold">{t("admin.generatedAt")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.evaluation_jobs.map((j) => (
                      <tr key={j.name} className="border-t border-line">
                        <td className="py-1.5">
                          <Mono>{j.name}</Mono>
                        </td>
                        <td className="py-1.5">
                          <Status ok={j.status === "completed" ? true : j.status === "failed" ? false : null} label={j.status} />
                        </td>
                        <td className="py-1.5">
                          <Mono>{j.report ?? "—"}</Mono>
                        </td>
                        <td className="py-1.5">{when(j.generated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-ink-3">—</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
