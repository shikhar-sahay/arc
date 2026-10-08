import { useState, useEffect } from "react";
import { Contract, Action, ContractStatus } from "../types";
import { api, buildContractPayload } from "../lib/api";

type ModalMode = "create" | "edit" | "view";

interface ContractEditorProps {
  mode: ModalMode;
  contractStatus: ContractStatus | null;
  onClose: () => void;
  onSaved: () => void;
}

const METRICS = [
  { value: "system.cpu.percent", label: "system.cpu.percent" },
  { value: "system.memory.percent", label: "system.memory.percent" },
  { value: "target.process.present", label: "target.process.present" },
];

const OPERATORS = [
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "eq", label: "=" },
  { value: "ne", label: "!=" },
];

const BOOLEAN_OPERATORS = OPERATORS.filter((operator) =>
  ["eq", "ne"].includes(operator.value),
);

type ActionType = "nice" | "cpu_affinity" | "suspend" | "resume" | "cpu_quota";

interface ActionDraft {
  type: ActionType;
  niceVal: string;
  affinityCpus: string;
  quotaVal: string;
}

function blankAction(): ActionDraft {
  return { type: "nice", niceVal: "10", affinityCpus: "0", quotaVal: "50" };
}

function draftToAction(d: ActionDraft): Action | null {
  switch (d.type) {
    case "nice": {
      const v = parseInt(d.niceVal, 10);
      if (isNaN(v) || v < -20 || v > 19) return null;
      return { type: "nice", value: v };
    }
    case "cpu_affinity": {
      const cpus = d.affinityCpus
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));
      if (cpus.length === 0) return null;
      return { type: "cpu_affinity", cpus };
    }
    case "suspend":
      return { type: "suspend" };
    case "resume":
      return { type: "resume" };
    case "cpu_quota": {
      const q = parseFloat(d.quotaVal);
      if (isNaN(q) || q <= 0 || q > 100) return null;
      return { type: "cpu_quota", quota_percent: q };
    }
    default:
      return null;
  }
}

function actionToDraft(act: Action): ActionDraft {
  switch (act.type) {
    case "nice":
      return {
        type: "nice",
        niceVal: String(act.value),
        affinityCpus: "0",
        quotaVal: "50",
      };
    case "cpu_affinity":
      return {
        type: "cpu_affinity",
        niceVal: "10",
        affinityCpus: act.cpus.join(", "),
        quotaVal: "50",
      };
    case "suspend":
      return {
        type: "suspend",
        niceVal: "10",
        affinityCpus: "0",
        quotaVal: "50",
      };
    case "resume":
      return {
        type: "resume",
        niceVal: "10",
        affinityCpus: "0",
        quotaVal: "50",
      };
    case "cpu_quota":
      return {
        type: "cpu_quota",
        niceVal: "10",
        affinityCpus: "0",
        quotaVal: String(act.quota_percent),
      };
  }
}

function yamlLike(c: Contract): string {
  const actionLines = c.actions
    .map((a) => {
      if (a.type === "nice") return `  - type: nice\n    value: ${a.value}`;
      if (a.type === "cpu_affinity")
        return `  - type: cpu_affinity\n    cpus: [${a.cpus.join(", ")}]`;
      if (a.type === "cpu_quota")
        return `  - type: cpu_quota\n    quota_percent: ${a.quota_percent}`;
      return `  - type: ${a.type}`;
    })
    .join("\n");

  return `version: ${c.version}
id: ${c.id}
name: ${c.name}
description: ${c.description ?? "null"}
enabled: ${c.enabled}
target:
  type: process
  match:
    executable: ${c.target.match.executable ?? "null"}
    command_contains: ${c.target.match.command_contains ?? "null"}
trigger:
  metric: ${c.trigger.metric}
  operator: ${c.trigger.operator}
  value: ${c.trigger.value}
  for_seconds: ${c.trigger.for_seconds}
actions:
${actionLines}
restore:
  metric: ${c.restore.metric}
  operator: ${c.restore.operator}
  value: ${c.restore.value}
  for_seconds: ${c.restore.for_seconds}
`;
}

const inputCls = "field font-mono";
const labelCls =
  "block text-neutral-400 mb-1.5 text-[10px] uppercase tracking-wider font-semibold";
const sectionCls =
  "panel-body border border-neutral-800 rounded-lg space-y-3 bg-neutral-950/30";

export function ContractEditor({
  mode,
  contractStatus,
  onClose,
  onSaved,
}: ContractEditorProps) {
  const c = contractStatus?.contract ?? null;
  const isView = mode === "view";

  const [formId, setFormId] = useState(c?.id ?? "");
  const [formName, setFormName] = useState(c?.name ?? "");
  const [formDesc, setFormDesc] = useState(c?.description ?? "");
  const [formExecutable, setFormExecutable] = useState(
    c?.target.match.executable ?? "python",
  );
  const [formCommand, setFormCommand] = useState(
    c?.target.match.command_contains ?? "",
  );
  const [formTriggerMetric, setFormTriggerMetric] = useState(
    c?.trigger.metric ?? "system.cpu.percent",
  );
  const [formTriggerOp, setFormTriggerOp] = useState(
    c?.trigger.operator ?? "gt",
  );
  const [formTriggerVal, setFormTriggerVal] = useState(
    String(c?.trigger.value ?? "75"),
  );
  const [formTriggerSec, setFormTriggerSec] = useState(
    String(c?.trigger.for_seconds ?? "5"),
  );
  const [formRestoreMetric, setFormRestoreMetric] = useState(
    c?.restore.metric ?? "system.cpu.percent",
  );
  const [formRestoreOp, setFormRestoreOp] = useState(
    c?.restore.operator ?? "lt",
  );
  const [formRestoreVal, setFormRestoreVal] = useState(
    String(c?.restore.value ?? "55"),
  );
  const [formRestoreSec, setFormRestoreSec] = useState(
    String(c?.restore.for_seconds ?? "5"),
  );
  const [actionDrafts, setActionDrafts] = useState<ActionDraft[]>(
    c?.actions && c.actions.length > 0
      ? c.actions.map(actionToDraft)
      : [blankAction()],
  );

  const [showYaml, setShowYaml] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (mode === "create") {
      setFormId("");
      setFormName("");
      setFormDesc("");
      setFormExecutable("python");
      setFormCommand("");
      setFormTriggerMetric("system.cpu.percent");
      setFormTriggerOp("gt");
      setFormTriggerVal("75");
      setFormTriggerSec("5");
      setFormRestoreMetric("system.cpu.percent");
      setFormRestoreOp("lt");
      setFormRestoreVal("55");
      setFormRestoreSec("5");
      setActionDrafts([blankAction()]);
    }
  }, [mode]);

  function updateActionDraft(idx: number, patch: Partial<ActionDraft>) {
    setActionDrafts((prev) =>
      prev.map((d, i) => (i === idx ? { ...d, ...patch } : d)),
    );
  }

  function addAction() {
    setActionDrafts((prev) => [...prev, blankAction()]);
  }

  function removeAction(idx: number) {
    setActionDrafts((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const resolvedActions: Action[] = [];
    for (let i = 0; i < actionDrafts.length; i++) {
      const act = draftToAction(actionDrafts[i]);
      if (act === null) {
        setFormError(`Action ${i + 1} has invalid parameters.`);
        return;
      }
      resolvedActions.push(act);
    }

    if (resolvedActions.length === 0) {
      setFormError("At least one action is required.");
      return;
    }

    const payload = buildContractPayload({
      id: formId,
      name: formName,
      description: formDesc,
      executable: formExecutable,
      command: formCommand,
      triggerMetric: formTriggerMetric,
      triggerOp: formTriggerOp,
      triggerVal: formTriggerVal,
      triggerSec: formTriggerSec,
      actions: resolvedActions,
      restoreMetric: formRestoreMetric,
      restoreOp: formRestoreOp,
      restoreVal: formRestoreVal,
      restoreSec: formRestoreSec,
      enabled: c?.enabled ?? true,
    });

    // Validate via backend
    try {
      const valResult = await api.validateContract(payload);
      if (!valResult.valid) {
        setFormError(valResult.error ?? "Validation failed");
        return;
      }
    } catch (err) {
      setFormError(
        err instanceof Error
          ? `Backend validation unavailable: ${err.message}`
          : "Backend validation unavailable",
      );
      return;
    }

    setSaving(true);
    try {
      if (mode === "create") {
        await api.createContract(payload);
      } else if (mode === "edit" && c) {
        await api.updateContract(c.id, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const title =
    mode === "create"
      ? "New Policy Contract"
      : mode === "edit"
        ? `Edit: ${c?.id}`
        : `Contract: ${c?.id}`;

  const yamlContent = c ? yamlLike(c) : "";

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-md z-50 flex items-start justify-center p-3 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="bg-[#1b1d1f] border border-[#34373a] rounded-xl max-w-3xl w-full p-5 sm:p-6 space-y-4 shadow-2xl mb-10">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200 font-mono">
            {title}
          </h2>
          <div className="flex items-center space-x-2">
            {isView && (
              <button
                onClick={() => setShowYaml((v) => !v)}
                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded text-[11px] font-mono"
              >
                {showYaml ? "Structured" : "YAML"}
              </button>
            )}
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 text-xl leading-none px-1"
              aria-label="Close dialog"
            >
              ✕
            </button>
          </div>
        </div>

        {/* View mode: structured or YAML */}
        {isView && c ? (
          showYaml ? (
            <pre className="bg-slate-950 p-4 rounded border border-slate-800 text-xs font-mono text-cyan-300 overflow-x-auto whitespace-pre">
              {yamlContent}
            </pre>
          ) : (
            <ContractStructuredView c={c} />
          )
        ) : (
          /* Edit / Create form */
          <form onSubmit={handleSubmit} className="space-y-4 text-xs font-mono">
            {formError && (
              <div className="bg-rose-950/60 border border-rose-800 rounded p-3 text-rose-300 text-xs">
                {formError}
              </div>
            )}

            <div className="page-kicker">1 · Identity</div>
            {/* ID + Name */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>ID (hyphen-case)</label>
                <input
                  type="text"
                  required
                  disabled={mode === "edit"}
                  value={formId}
                  onChange={(e) => setFormId(e.target.value)}
                  placeholder="e.g. worker-cpu-relief"
                  className={
                    inputCls +
                    (mode === "edit" ? " opacity-50 cursor-not-allowed" : "")
                  }
                />
              </div>
              <div>
                <label className={labelCls}>Name</label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. CPU Affinity Constraint"
                  className={inputCls}
                />
              </div>
            </div>

            <div>
              <label className={labelCls}>Description (optional)</label>
              <input
                type="text"
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder="Brief description of this contract"
                className={inputCls}
              />
            </div>

            {/* Target */}
            <div className={sectionCls}>
              <div className="font-bold text-slate-400 uppercase text-[10px] tracking-widest mb-1">
                2 · Target process
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Executable name</label>
                  <input
                    type="text"
                    value={formExecutable}
                    onChange={(e) => setFormExecutable(e.target.value)}
                    placeholder="e.g. python"
                    className={inputCls}
                  />
                </div>
                <div>
                  <label className={labelCls}>Command line contains</label>
                  <input
                    type="text"
                    value={formCommand}
                    onChange={(e) => setFormCommand(e.target.value)}
                    placeholder="e.g. demo_cpu_worker"
                    className={inputCls}
                  />
                </div>
              </div>
            </div>

            {/* Trigger */}
            <div className={sectionCls}>
              <div className="font-bold text-slate-400 uppercase text-[10px] tracking-widest mb-1">
                3 · Trigger condition
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                <div>
                  <label className={labelCls}>Metric</label>
                  <select
                    value={formTriggerMetric}
                    onChange={(e) => {
                      const metric = e.target.value;
                      setFormTriggerMetric(metric);
                      if (metric === "target.process.present") {
                        setFormTriggerOp("eq");
                        setFormTriggerVal("true");
                      }
                    }}
                    className={inputCls}
                  >
                    {METRICS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Operator</label>
                  <select
                    value={formTriggerOp}
                    onChange={(e) => setFormTriggerOp(e.target.value)}
                    className={inputCls}
                  >
                    {(formTriggerMetric === "target.process.present"
                      ? BOOLEAN_OPERATORS
                      : OPERATORS
                    ).map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Value</label>
                  {formTriggerMetric === "target.process.present" ? (
                    <select
                      value={formTriggerVal}
                      onChange={(e) => setFormTriggerVal(e.target.value)}
                      className={inputCls}
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    <input
                      type="number"
                      required
                      min="0"
                      max="100"
                      step="0.5"
                      value={formTriggerVal}
                      onChange={(e) => setFormTriggerVal(e.target.value)}
                      className={inputCls}
                    />
                  )}
                </div>
                <div>
                  <label className={labelCls}>For (seconds)</label>
                  <input
                    type="number"
                    required
                    min="0"
                    step="1"
                    value={formTriggerSec}
                    onChange={(e) => setFormTriggerSec(e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className={sectionCls}>
              <div className="flex items-center justify-between mb-1">
                <div className="font-bold text-slate-400 uppercase text-[10px] tracking-widest">
                  4 · Resource actions
                </div>
                {actionDrafts.length < 4 && (
                  <button
                    type="button"
                    onClick={addAction}
                    className="text-[10px] text-cyan-400 hover:text-cyan-300 font-mono"
                  >
                    + Add action
                  </button>
                )}
              </div>

              {actionDrafts.map((draft, idx) => (
                <div
                  key={idx}
                  className="bg-slate-900 border border-slate-800 rounded p-3 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-500 font-mono">
                      Action {idx + 1}
                    </span>
                    {actionDrafts.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeAction(idx)}
                        className="text-[10px] text-rose-400 hover:text-rose-300 font-mono"
                      >
                        remove
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className={labelCls}>Action type</label>
                      <select
                        value={draft.type}
                        onChange={(e) =>
                          updateActionDraft(idx, {
                            type: e.target.value as ActionType,
                          })
                        }
                        className={inputCls}
                      >
                        <option value="nice">nice (priority adjustment)</option>
                        <option value="cpu_affinity">
                          cpu_affinity (core pinning)
                        </option>
                        <option value="suspend">suspend (SIGSTOP)</option>
                        <option value="resume">resume (SIGCONT)</option>
                        <option value="cpu_quota">
                          cpu_quota (cgroups v2 cpu.max)
                        </option>
                      </select>
                    </div>

                    <div>
                      {draft.type === "nice" && (
                        <>
                          <label className={labelCls}>
                            Nice value (-20 to 19)
                          </label>
                          <input
                            type="number"
                            min="-20"
                            max="19"
                            value={draft.niceVal}
                            onChange={(e) =>
                              updateActionDraft(idx, {
                                niceVal: e.target.value,
                              })
                            }
                            className={inputCls}
                          />
                          <p className="text-slate-600 text-[10px] mt-1">
                            Higher = lower priority. Restoring to lower nice may
                            need CAP_SYS_NICE.
                          </p>
                        </>
                      )}
                      {draft.type === "cpu_affinity" && (
                        <>
                          <label className={labelCls}>
                            CPU list (comma-separated)
                          </label>
                          <input
                            type="text"
                            value={draft.affinityCpus}
                            onChange={(e) =>
                              updateActionDraft(idx, {
                                affinityCpus: e.target.value,
                              })
                            }
                            placeholder="0, 1"
                            className={inputCls}
                          />
                          <p className="text-slate-600 text-[10px] mt-1">
                            e.g. 0 pins to core 0. Usually works without
                            elevated privilege.
                          </p>
                        </>
                      )}
                      {draft.type === "cpu_quota" && (
                        <>
                          <label className={labelCls}>
                            Quota percent (1-100)
                          </label>
                          <input
                            type="number"
                            min="1"
                            max="100"
                            value={draft.quotaVal}
                            onChange={(e) =>
                              updateActionDraft(idx, {
                                quotaVal: e.target.value,
                              })
                            }
                            className={inputCls}
                          />
                          <p className="text-slate-600 text-[10px] mt-1">
                            Requires writable cgroups v2 delegation. Check
                            capability panel.
                          </p>
                        </>
                      )}
                      {(draft.type === "suspend" ||
                        draft.type === "resume") && (
                        <div className="text-slate-500 text-[10px] pt-5">
                          No additional parameters. Signal sent to all matched
                          PIDs.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Restore */}
            <div className={sectionCls}>
              <div className="font-bold text-slate-400 uppercase text-[10px] tracking-widest mb-1">
                5 · Restoration condition
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                <div>
                  <label className={labelCls}>Metric</label>
                  <select
                    value={formRestoreMetric}
                    onChange={(e) => {
                      const metric = e.target.value;
                      setFormRestoreMetric(metric);
                      if (metric === "target.process.present") {
                        setFormRestoreOp("eq");
                        setFormRestoreVal("false");
                      }
                    }}
                    className={inputCls}
                  >
                    {METRICS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Operator</label>
                  <select
                    value={formRestoreOp}
                    onChange={(e) => setFormRestoreOp(e.target.value)}
                    className={inputCls}
                  >
                    {(formRestoreMetric === "target.process.present"
                      ? BOOLEAN_OPERATORS
                      : OPERATORS
                    ).map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Value</label>
                  {formRestoreMetric === "target.process.present" ? (
                    <select
                      value={formRestoreVal}
                      onChange={(e) => setFormRestoreVal(e.target.value)}
                      className={inputCls}
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    <input
                      type="number"
                      required
                      min="0"
                      max="100"
                      step="0.5"
                      value={formRestoreVal}
                      onChange={(e) => setFormRestoreVal(e.target.value)}
                      className={inputCls}
                    />
                  )}
                </div>
                <div>
                  <label className={labelCls}>For (seconds)</label>
                  <input
                    type="number"
                    required
                    min="0"
                    step="1"
                    value={formRestoreSec}
                    onChange={(e) => setFormRestoreSec(e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>
            </div>

            <div className={sectionCls}>
              <div className="font-bold text-neutral-400 uppercase text-[10px] tracking-widest">
                6 · Review
              </div>
              <div className="details text-[11px] leading-6">
                WHEN {formTriggerMetric} {formTriggerOp} {formTriggerVal} FOR{" "}
                {formTriggerSec}s{"\n"}
                DO {actionDrafts
                  .map((action) => action.type)
                  .join(", ")} TO{" "}
                {formExecutable || formCommand || "target process"}
                {"\n"}
                UNTIL {formRestoreMetric} {formRestoreOp} {formRestoreVal} FOR{" "}
                {formRestoreSec}s{"\n"}
                THEN RESTORE exact prior resource state
              </div>
              <p className="text-neutral-500 text-[10px] leading-relaxed">
                The backend validates this contract before saving. Active
                contracts cannot be changed until restoration completes.
              </p>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => setShowYaml((v) => !v)}
                className="text-[11px] text-slate-500 hover:text-slate-300 font-mono underline"
              >
                {showYaml ? "hide preview" : "preview YAML"}
              </button>
              <div className="flex items-center space-x-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-mono"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-white rounded text-xs font-mono font-bold disabled:opacity-50"
                >
                  {saving
                    ? "Saving..."
                    : mode === "create"
                      ? "Create Contract"
                      : "Save Changes"}
                </button>
              </div>
            </div>

            {showYaml && c && (
              <pre className="bg-slate-950 p-4 rounded border border-slate-800 text-xs font-mono text-cyan-300 overflow-x-auto whitespace-pre mt-2">
                {yamlContent}
              </pre>
            )}
          </form>
        )}

        {isView && (
          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-mono"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ContractStructuredView({ c }: { c: Contract }) {
  return (
    <div className="space-y-3 text-xs font-mono">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <div className="text-slate-500 uppercase text-[10px] mb-1">ID</div>
          <div className="text-slate-200">{c.id}</div>
        </div>
        <div>
          <div className="text-slate-500 uppercase text-[10px] mb-1">Name</div>
          <div className="text-slate-200">{c.name}</div>
        </div>
      </div>

      {c.description && (
        <div>
          <div className="text-slate-500 uppercase text-[10px] mb-1">
            Description
          </div>
          <div className="text-slate-400">{c.description}</div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 border-t border-neutral-800 pt-3">
        <div className="bg-slate-950 border border-slate-800 rounded p-3">
          <div className="text-[10px] text-slate-500 uppercase mb-2 tracking-widest">
            FOR
          </div>
          <div className="text-slate-300">
            {c.target.match.executable && (
              <div>
                <span className="text-slate-500">exe: </span>
                <span className="text-cyan-300">
                  {c.target.match.executable}
                </span>
              </div>
            )}
            {c.target.match.command_contains && (
              <div>
                <span className="text-slate-500">cmd: </span>
                <span>{c.target.match.command_contains}</span>
              </div>
            )}
          </div>
        </div>

        <div className="bg-slate-950 border border-slate-800 rounded p-3">
          <div className="text-[10px] text-slate-500 uppercase mb-2 tracking-widest">
            WHEN
          </div>
          <div className="text-slate-300">
            {c.trigger.metric}
            <br />
            <span className="text-cyan-400">{c.trigger.operator}</span>{" "}
            {String(c.trigger.value)}
            <br />
            <span className="text-slate-500">for {c.trigger.for_seconds}s</span>
          </div>
        </div>

        <div className="bg-slate-950 border border-slate-800 rounded p-3">
          <div className="text-[10px] text-slate-500 uppercase mb-2 tracking-widest">
            UNTIL
          </div>
          <div className="text-slate-300">
            {c.restore.metric}
            <br />
            <span className="text-cyan-400">{c.restore.operator}</span>{" "}
            {String(c.restore.value)}
            <br />
            <span className="text-slate-500">for {c.restore.for_seconds}s</span>
          </div>
        </div>
      </div>

      <div className="border-t border-slate-800 pt-3">
        <div className="text-[10px] text-slate-500 uppercase mb-2 tracking-widest">
          DO (Actions)
        </div>
        <div className="flex flex-wrap gap-2">
          {c.actions.map((act, i) => (
            <span
              key={i}
              className="bg-slate-950 border border-slate-700 px-2 py-1 rounded text-cyan-300"
            >
              {act.type === "nice" &&
                `nice ${act.value > 0 ? "+" : ""}${act.value}`}
              {act.type === "cpu_affinity" &&
                `affinity [${act.cpus.join(",")}]`}
              {act.type === "suspend" && "SIGSTOP suspend"}
              {act.type === "resume" && "SIGCONT resume"}
              {act.type === "cpu_quota" && `cpu.max ${act.quota_percent}%`}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
