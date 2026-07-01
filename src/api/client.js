export async function requestCodeAction(payload) {
  const response = await fetch('/api/code/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(errorData.detail || 'Request failed')
  }

  return response.json()
}

export const apiClient = {
  requestCodeAction,
};
