import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getModelSettings, testModelProvider, updateModelSettings } from "../lib/api";
import type {
  ModelProviderSettings,
  ModelProviderTestResult,
  ModelSettings,
  ModelTaskType,
} from "../lib/types";

const taskOptions: Array<{ key: ModelTaskType; label: string }> = [
  { key: "planner", label: "Planner" },
  { key: "reviewer", label: "Reviewer" },
  { key: "consistency", label: "Consistency" },
  { key: "survey_synthesizer", label: "Survey Synthesizer" },
  { key: "writer", label: "Writer" },
  { key: "code", label: "Code" },
];

function createEmptyModels(
  source?: Partial<Record<ModelTaskType, string>>,
): Record<ModelTaskType, string> {
  return {
    planner: source?.planner ?? "",
    reviewer: source?.reviewer ?? "",
    consistency: source?.consistency ?? "",
    survey_synthesizer: source?.survey_synthesizer ?? "",
    writer: source?.writer ?? "",
    code: source?.code ?? "",
  };
}

function createEmptyRoutes(
  source?: Partial<Record<ModelTaskType, string>>,
): Record<ModelTaskType, string> {
  return {
    planner: source?.planner ?? "",
    reviewer: source?.reviewer ?? "",
    consistency: source?.consistency ?? "",
    survey_synthesizer: source?.survey_synthesizer ?? "",
    writer: source?.writer ?? "",
    code: source?.code ?? "",
  };
}

function normalizeSettings(settings: ModelSettings): ModelSettings {
  return {
    providers: settings.providers.map((provider) => ({
      ...provider,
      models: createEmptyModels(provider.models),
    })),
    task_routes: createEmptyRoutes(settings.task_routes),
  };
}

function createProviderDraft(index: number): ModelProviderSettings {
  return {
    id: `provider-${index + 1}`,
    label: "Custom Provider",
    api_base: "https://api.example.com/v1",
    api_key: "",
    priority: index + 1,
    enabled: true,
    models: createEmptyModels(),
  };
}

function getProviderKey(provider: ModelProviderSettings, index: number) {
  return `${provider.id || "provider"}-${index}`;
}

function formatRequestError(error: Error) {
  try {
    const parsed = JSON.parse(error.message) as { detail?: string };
    if (parsed.detail) {
      return parsed.detail;
    }
  } catch {
    return error.message;
  }
  return error.message;
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<ModelSettings | null>(null);
  const [feedback, setFeedback] = useState<string>("");
  const [testingProviderKey, setTestingProviderKey] = useState<string>("");
  const [providerTestResults, setProviderTestResults] = useState<
    Record<string, ModelProviderTestResult>
  >({});

  const settingsQuery = useQuery({
    queryKey: ["model-settings"],
    queryFn: getModelSettings,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: ModelSettings) => updateModelSettings(payload),
    onSuccess: async (data) => {
      const normalized = normalizeSettings(data);
      setDraft(normalized);
      setFeedback("Settings saved and applied.");
      await queryClient.invalidateQueries({ queryKey: ["model-settings"] });
    },
    onError: (error: Error) => {
      setFeedback(formatRequestError(error));
    },
  });

  const testMutation = useMutation({
    mutationFn: ({
      provider,
      providerKey,
    }: {
      provider: ModelProviderSettings;
      providerKey: string;
    }) => testModelProvider({ provider }),
    onMutate: ({ providerKey }) => {
      setTestingProviderKey(providerKey);
    },
    onSuccess: (result, { providerKey }) => {
      setProviderTestResults((current) => ({ ...current, [providerKey]: result }));
      setTestingProviderKey("");
    },
    onError: (error: Error, { provider, providerKey }) => {
      setProviderTestResults((current) => ({
        ...current,
        [providerKey]: {
          ok: false,
          provider: provider.id,
          model: "",
          message: formatRequestError(error),
          response_preview: null,
        },
      }));
      setTestingProviderKey("");
    },
  });

  useEffect(() => {
    if (!settingsQuery.data) {
      return;
    }
    setDraft(normalizeSettings(settingsQuery.data));
  }, [settingsQuery.data]);

  const providers = draft?.providers ?? [];

  function updateProvider(
    index: number,
    field: keyof Omit<ModelProviderSettings, "models">,
    value: string | number | boolean,
  ) {
    setDraft((current) => {
      if (!current) return current;
      const nextProviders = current.providers.map((provider, providerIndex) =>
        providerIndex === index ? { ...provider, [field]: value } : provider,
      );
      return { ...current, providers: nextProviders };
    });
  }

  function updateProviderModel(index: number, task: ModelTaskType, value: string) {
    setDraft((current) => {
      if (!current) return current;
      const nextProviders = current.providers.map((provider, providerIndex) =>
        providerIndex === index
          ? { ...provider, models: { ...provider.models, [task]: value } }
          : provider,
      );
      return { ...current, providers: nextProviders };
    });
  }

  function updateTaskRoute(task: ModelTaskType, providerId: string) {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        task_routes: { ...current.task_routes, [task]: providerId },
      };
    });
  }

  function addProvider() {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        providers: [...current.providers, createProviderDraft(current.providers.length)],
      };
    });
  }

  function removeProvider(index: number) {
    setDraft((current) => {
      if (!current) return current;
      const removed = current.providers[index];
      const nextProviders = current.providers.filter((_, providerIndex) => providerIndex !== index);
      const nextRoutes = { ...current.task_routes };
      for (const task of taskOptions) {
        if (nextRoutes[task.key] === removed.id) {
          nextRoutes[task.key] = "";
        }
      }
      return {
        ...current,
        providers: nextProviders,
        task_routes: nextRoutes,
      };
    });
  }

  async function handleSave() {
    if (!draft) return;
    setFeedback("");
    await saveMutation.mutateAsync(draft);
  }

  async function handleTestProvider(provider: ModelProviderSettings, index: number) {
    const providerKey = getProviderKey(provider, index);
    await testMutation.mutateAsync({ provider, providerKey });
  }

  return (
    <div className="page page--settings">
      <section className="page__hero">
        <p className="eyebrow">Model Settings</p>
        <h1>Manage model providers, keys, and task routing.</h1>
        <p className="page__subline">
          Changes are saved to local configuration and apply to the running backend immediately.
        </p>
      </section>

      {settingsQuery.isLoading ? <p className="muted">Loading model settings...</p> : null}
      {settingsQuery.isError ? (
        <p className="error-text">Failed to load model settings. Please confirm the backend is running.</p>
      ) : null}

      {draft ? (
        <div className="settings-layout">
          <section className="panel glass-card">
            <div className="panel__header panel__header--actions">
              <div>
                <p className="eyebrow">Providers</p>
                <h3>Provider Configuration</h3>
              </div>
              <button type="button" className="button button--ghost" onClick={addProvider}>
                Add Provider
              </button>
            </div>

            <div className="settings-stack">
              {providers.map((provider, index) => (
                <article key={`${provider.id}-${index}`} className="provider-editor">
                  <div className="provider-editor__header">
                    <strong>{provider.label || provider.id || `Provider ${index + 1}`}</strong>
                    <div className="provider-editor__actions">
                      <button
                        type="button"
                        className="button button--ghost"
                        onClick={() => handleTestProvider(provider, index)}
                        disabled={testingProviderKey === getProviderKey(provider, index)}
                      >
                        {testingProviderKey === getProviderKey(provider, index)
                          ? "Testing..."
                          : "Test Connection"}
                      </button>
                      <button
                        type="button"
                        className="button button--ghost"
                        onClick={() => removeProvider(index)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>

                  <div className="settings-grid">
                    <label className="field">
                      <span>Provider ID</span>
                      <input
                        value={provider.id}
                        onChange={(event) => updateProvider(index, "id", event.target.value)}
                        placeholder="openai"
                      />
                    </label>
                    <label className="field">
                      <span>Display Name</span>
                      <input
                        value={provider.label}
                        onChange={(event) => updateProvider(index, "label", event.target.value)}
                        placeholder="OpenAI"
                      />
                    </label>
                    <label className="field field--wide">
                      <span>Base URL</span>
                      <input
                        value={provider.api_base}
                        onChange={(event) => updateProvider(index, "api_base", event.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </label>
                    <label className="field field--wide">
                      <span>API Key</span>
                      <input
                        value={provider.api_key}
                        onChange={(event) => updateProvider(index, "api_key", event.target.value)}
                        placeholder="sk-..."
                      />
                    </label>
                    <label className="field">
                      <span>Priority</span>
                      <input
                        type="number"
                        value={provider.priority}
                        onChange={(event) =>
                          updateProvider(index, "priority", Number(event.target.value) || 0)
                        }
                      />
                    </label>
                    <label className="field checkbox-field">
                      <span>Enabled</span>
                      <input
                        type="checkbox"
                        checked={provider.enabled}
                        onChange={(event) => updateProvider(index, "enabled", event.target.checked)}
                      />
                    </label>
                  </div>

                  {providerTestResults[getProviderKey(provider, index)] ? (
                    <div className="provider-test-result">
                      <p
                        className={
                          providerTestResults[getProviderKey(provider, index)].ok
                            ? "success-text"
                            : "error-text"
                        }
                      >
                        {providerTestResults[getProviderKey(provider, index)].message}
                      </p>
                      <p className="muted">
                        Provider: {providerTestResults[getProviderKey(provider, index)].provider} |
                        Model: {providerTestResults[getProviderKey(provider, index)].model || "N/A"}
                      </p>
                      {providerTestResults[getProviderKey(provider, index)].response_preview ? (
                        <p className="muted">
                          Preview:{" "}
                          {providerTestResults[getProviderKey(provider, index)].response_preview}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="provider-models">
                    {taskOptions.map((task) => (
                      <label key={`${provider.id}-${task.key}`} className="field">
                        <span>{task.label} Model</span>
                        <input
                          value={provider.models[task.key] ?? ""}
                          onChange={(event) =>
                            updateProviderModel(index, task.key, event.target.value)
                          }
                          placeholder="model-name"
                        />
                      </label>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="panel glass-card">
            <div className="panel__header">
              <div>
                <p className="eyebrow">Task Routes</p>
                <h3>Primary Provider By Task</h3>
              </div>
            </div>

            <div className="settings-stack">
              {taskOptions.map((task) => (
                <label key={task.key} className="field">
                  <span>{task.label}</span>
                  <select
                    value={draft.task_routes[task.key] ?? ""}
                    onChange={(event) => updateTaskRoute(task.key, event.target.value)}
                  >
                    <option value="">Select provider</option>
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.label} ({provider.id})
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>

            <div className="settings-actions">
              <button
                type="button"
                className="button button--primary"
                onClick={handleSave}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? "Saving..." : "Save Settings"}
              </button>
              {feedback ? (
                <p className={saveMutation.isError ? "error-text" : "muted"}>{feedback}</p>
              ) : (
                <p className="muted">
                  The backend validates provider IDs, task assignments, and required model names.
                </p>
              )}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
