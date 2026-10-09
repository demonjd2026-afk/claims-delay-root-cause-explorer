// Thin API client. Every call carries the global filters.
export class ApiError extends Error {}

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail ?? detail; } catch { /* keep status text */ }
    throw new ApiError(typeof detail === "string" ? detail : "The request could not be completed.");
  }
  return response.json();
}

function query(filters, extra = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...extra })) {
    if (value !== "" && value !== null && value !== undefined && value !== false) params.set(key, value);
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const api = {
  meta: () => request("/api/meta"),
  overview: (f) => request(`/api/overview${query(f)}`),
  journey: (f) => request(`/api/journey${query(f)}`),
  theme: (key, f) => request(`/api/themes/${key}${query(f)}`),
  trends: (f) => request(`/api/trends${query(f)}`),
  hotspots: (f, dimension) => request(`/api/hotspots${query(f, { dimension })}`),
  interventions: (f) => request(`/api/interventions${query(f)}`),
  claims: (f, extra) => request(`/api/claims${query(f, extra)}`),
  claim: (id) => request(`/api/claims/${encodeURIComponent(id)}`),
  model: () => request("/api/model"),
  rebuild: (body) => request("/api/data/rebuild", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  chat: (body) => request("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
};
