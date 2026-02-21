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
  MemberActivityResponse,
  EmberStatusResponse,
  TreeSummary,
  TreeNode,
  MorselSummary,
  CardSummary,
  CreateCardRequest,
  UpdateCardRequest,
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

export async function killTask(id: number): Promise<TaskDetail> {
  const { data } = await apiClient.post<TaskDetail>(`/tasks/${id}/kill`);
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

export async function getEmberStatus(): Promise<EmberStatusResponse> {
  const { data } = await apiClient.get<EmberStatusResponse>('/embers/status');
  return data;
}

export async function getTrees(params: {
  limit?: number;
  offset?: number;
} = {}): Promise<TreeSummary[]> {
  const { data } = await apiClient.get<TreeSummary[]>('/trees', { params });
  return data;
}

export async function getTree(rootId: number): Promise<TreeNode> {
  const { data } = await apiClient.get<TreeNode>(`/trees/${rootId}`);
  return data;
}

export async function getMorsels(params: {
  creator?: string;
  tag?: string;
  object_type?: string;
  object_id?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<MorselSummary[]> {
  const { data } = await apiClient.get<MorselSummary[]>('/morsels', { params });
  return data;
}

export async function getMorsel(id: number): Promise<MorselSummary> {
  const { data } = await apiClient.get<MorselSummary>(`/morsels/${id}`);
  return data;
}

// -- Kanban --

export async function getCards(params: {
  col?: string;
  assignee?: string;
  creator?: string;
  priority?: string;
  label?: string;
  include_archived?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<CardSummary[]> {
  const { data } = await apiClient.get<CardSummary[]>('/kanban/cards', { params });
  return data;
}

export async function getCard(id: number): Promise<CardSummary> {
  const { data } = await apiClient.get<CardSummary>(`/kanban/cards/${id}`);
  return data;
}

export async function createCard(req: CreateCardRequest): Promise<CardSummary> {
  const { data } = await apiClient.post<CardSummary>('/kanban/cards', req);
  return data;
}

export async function updateCard(id: number, req: UpdateCardRequest): Promise<CardSummary> {
  const { data } = await apiClient.patch<CardSummary>(`/kanban/cards/${id}`, req);
  return data;
}

export async function deleteCard(id: number): Promise<void> {
  await apiClient.delete(`/kanban/cards/${id}`);
}
