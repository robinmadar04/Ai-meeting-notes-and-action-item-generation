export type Action = { id:number; meeting_id:number; task:string; owner:string|null; deadline:string|null; priority:string; status:'pending'|'in_progress'|'completed'; evidence:string|null }
export type Decision = { decision:string; evidence?:string|null }
export type Meeting = { id:number; title:string; meeting_date:string|null; transcript:string; summary:string; key_points:string[]; decisions:Decision[]; unresolved_questions:string[]; created_at:string; updated_at:string; action_items:Action[] }
export type MeetingRow = Omit<Meeting,'transcript'|'key_points'|'decisions'|'unresolved_questions'|'action_items'> & { action_count:number }
const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
export async function api<T>(path:string, options:RequestInit = {}):Promise<T> {
  const res = await fetch(`${base}${path}`, options)
  if (!res.ok) { let message=`Request failed (${res.status})`; try { message=(await res.json()).detail || message } catch {} throw new Error(message) }
  if (res.status===204) return undefined as T
  return res.json()
}
export const json = (method:string, body:unknown):RequestInit => ({method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})
