export interface MessageSummary {
  id: number;
  sender: string;
  subject: string;
  body: string;
  created_at: string;
  is_read: boolean;
}

export interface ReadByEntry {
  brother: string;
  read_at: string;
}

export interface MessageDetail {
  id: number;
  sender: string;
  subject: string;
  body: string;
  created_at: string;
  recipients: string[];
  is_read: boolean;
  read_by: ReadByEntry[];
}

export interface FeedMessage {
  id: number;
  sender: string;
  subject: string;
  body: string;
  created_at: string;
  recipients: string[];
  read_by: ReadByEntry[];
}

export interface SendMessageRequest {
  recipients: string[];
  subject: string;
  body: string;
}

export interface EditMessageRequest {
  subject?: string;
  body?: string;
}

export interface SendMessageResponse {
  id: number;
  message: string;
}

export interface UnreadCountResponse {
  unread: number;
}

export interface TaskSummary {
  id: number;
  creator: string;
  assignee: string;
  subject: string;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface TaskEvent {
  id: number;
  task_id: number;
  event_type: string;
  tool_name: string | null;
  summary: string;
  created_at: string;
}

export interface TaskDetail extends TaskSummary {
  prompt: string;
  session_name: string | null;
  host: string | null;
  working_dir: string | null;
  output: string | null;
  messages: FeedMessage[];
  events: TaskEvent[];
}
