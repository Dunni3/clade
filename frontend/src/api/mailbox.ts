import apiClient from './client';
import type {
  MessageSummary,
  MessageDetail,
  FeedMessage,
  SendMessageRequest,
  SendMessageResponse,
  EditMessageRequest,
  UnreadCountResponse,
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
