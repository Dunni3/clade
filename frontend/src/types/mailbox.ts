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
  parent_task_id: number | null;
  root_task_id: number | null;
  depth: number;
  blocked_by_task_id: number | null;
}

export interface TaskEvent {
  id: number;
  task_id: number;
  event_type: string;
  tool_name: string | null;
  summary: string;
  created_at: string;
}

export interface LinkedCardInfo {
  id: number;
  title: string;
  col: string;
  priority: string;
}

export interface TaskDetail extends TaskSummary {
  prompt: string;
  session_name: string | null;
  host: string | null;
  working_dir: string | null;
  output: string | null;
  metadata: Record<string, unknown> | null;
  on_complete: string | null;
  children: TaskSummary[];
  blocked_tasks: TaskSummary[];
  messages: FeedMessage[];
  events: TaskEvent[];
  linked_cards: LinkedCardInfo[];
}

export interface MemberActivity {
  name: string;
  last_message_at: string | null;
  messages_sent: number;
  active_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  last_task_at: string | null;
}

export interface MemberActivityResponse {
  members: MemberActivity[];
}

export interface EmberInfo {
  status: string;
  active_tasks?: number;
  uptime_seconds?: number;
  registered_status?: string;
  last_seen?: string;
}

export interface EmberStatusResponse {
  embers: Record<string, EmberInfo>;
}

export interface TreeSummary {
  root_task_id: number;
  subject: string;
  creator: string;
  created_at: string;
  total_tasks: number;
  completed: number;
  failed: number;
  in_progress: number;
  pending: number;
  killed: number;
  blocked: number;
}

export interface TreeNode {
  id: number;
  creator: string;
  assignee: string;
  subject: string;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  parent_task_id: number | null;
  root_task_id: number | null;
  blocked_by_task_id: number | null;
  prompt: string | null;
  session_name: string | null;
  host: string | null;
  working_dir: string | null;
  output: string | null;
  metadata: Record<string, unknown> | null;
  depth: number;
  children: TreeNode[];
  linked_cards?: LinkedCardInfo[];
}

export interface MorselLink {
  object_type: string;
  object_id: string;
}

export interface MorselSummary {
  id: number;
  creator: string;
  body: string;
  created_at: string;
  tags: string[];
  links: MorselLink[];
}

// -- Kanban --

export interface CardLink {
  object_type: string;
  object_id: string;
}

export interface CardSummary {
  id: number;
  title: string;
  description: string;
  col: string;
  priority: string;
  assignee: string | null;
  creator: string;
  created_at: string;
  updated_at: string;
  labels: string[];
  links: CardLink[];
  project: string | null;
}

export interface CreateCardRequest {
  title: string;
  description?: string;
  col?: string;
  priority?: string;
  assignee?: string | null;
  labels?: string[];
  links?: CardLink[];
  project?: string | null;
}

export interface UpdateCardRequest {
  title?: string;
  description?: string;
  col?: string;
  priority?: string;
  assignee?: string | null;
  labels?: string[];
  links?: CardLink[];
  project?: string | null;
}

// -- Search --

export interface SearchResult {
  type: string; // "task" | "morsel" | "card"
  id: number;
  title: string;
  snippet: string;
  rank: number;
  status?: string | null;
  col?: string | null;
  priority?: string | null;
  assignee?: string | null;
  creator?: string | null;
  created_at?: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
}
