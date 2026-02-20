import apiClient from './client';
import type {
  MessageSummary,
  MessageDetail,
  FeedMessage,
  SendMessageRequest,
  SendMessageResponse,
  EditMessageRequest,
  UnreadCountResponse,
  TaskSummary,
  TaskDetail,
  ThrumSummary,
  ThrumDetail,
  MemberActivityResponse,
} from '../types/mailbox';

export async function getInbox(unreadOnly = false, limit = 50): Promise<MessageSummary[]> {
  const { data } = await apiClient.get<MessageSummary[]>('/messages', {
    params: { unread_only: unreadOnly, limit },
  });
  return data;
}

export async function getMessage(id: number): Promise<MessageDetail> {
  const { data } = await apiClient.get<MessageDetail>(`/messages/${id}`);
  return data;
}

export async function viewMessage(id: number): Promise<FeedMessage> {
  const { data } = await apiClient.post<FeedMessage>(`/messages/${id}/view`);
  return data;
}

export async function getFeed(params: {
  sender?: string;
  recipient?: string;
  q?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<FeedMessage[]> {
  const { data } = await apiClient.get<FeedMessage[]>('/messages/feed', { params });
  return data;
}

export async function sendMessage(req: SendMessageRequest): Promise<SendMessageResponse> {
  const { data } = await apiClient.post<SendMessageResponse>('/messages', req);
  return data;
}

export async function editMessage(id: number, req: EditMessageRequest): Promise<FeedMessage> {
  const { data } = await apiClient.patch<FeedMessage>(`/messages/${id}`, req);
  return data;
}

export async function deleteMessage(id: number): Promise<void> {
  await apiClient.delete(`/messages/${id}`);
}

export async function markRead(id: number): Promise<void> {
  await apiClient.post(`/messages/${id}/read`);
}

export async function markUnread(id: number): Promise<void> {
  await apiClient.post(`/messages/${id}/unread`);
}

export async function getUnreadCount(): Promise<number> {
  const { data } = await apiClient.get<UnreadCountResponse>('/unread');
  return data.unread;
}

export async function getTasks(params: {
  assignee?: string;
  status?: string;
  creator?: string;
  limit?: number;
} = {}): Promise<TaskSummary[]> {
  const { data } = await apiClient.get<TaskSummary[]>('/tasks', { params });
  return data;
}

export async function getTask(id: number): Promise<TaskDetail> {
  const { data } = await apiClient.get<TaskDetail>(`/tasks/${id}`);
  return data;
}

export async function getThrums(params: {
  status?: string;
  creator?: string;
  limit?: number;
} = {}): Promise<ThrumSummary[]> {
  const { data } = await apiClient.get<ThrumSummary[]>('/thrums', { params });
  return data;
}

export async function getThrum(id: number): Promise<ThrumDetail> {
  const { data } = await apiClient.get<ThrumDetail>(`/thrums/${id}`);
  return data;
}

export async function getHealthCheck(): Promise<{ status: string }> {
  const { data } = await apiClient.get<{ status: string }>('/health');
  return data;
}

export async function getMemberActivity(): Promise<MemberActivityResponse> {
  const { data } = await apiClient.get<MemberActivityResponse>('/members/activity');
  return data;
}
