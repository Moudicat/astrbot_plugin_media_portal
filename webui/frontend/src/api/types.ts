// 与 webui/server.py 路由响应保持一致的 DTO 类型。

export type MediaKind = "image" | "video" | "audio" | "file" | string;

export interface MediaItem {
  id: number | string;
  filename: string;
  category: string;
  kind: MediaKind;
  size: number;
  size_human?: string;
  mime?: string;
  description?: string;
  tags?: string[];
  created_at?: number | string;
  updated_at?: number | string;
  duration?: number;
  public_url?: string;
  // 预览相关：在 data 浏览场景下我们会动态塞 directUrl
  directUrl?: string;
  name?: string;
  path?: string;
  is_dir?: boolean;
}

export interface MediaListResp {
  items: MediaItem[];
  total: number;
  total_pages: number;
  page?: number;
  page_size?: number;
}

export interface MediaStats {
  total_count?: number;
  total_size?: number | string;
  total_size_human?: string;
  by_kind?: Record<string, number>;
  categories?: Array<{ category: string; count: number }>;
}

export interface CategoryItem {
  category: string;
  description?: string;
  count: number;
}

export interface CategoryListResp {
  items: CategoryItem[];
}

export interface DataTreeItem {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number;
  mime?: string;
  kind?: MediaKind;
}

export interface DataTreeResp {
  items: DataTreeItem[];
  path: string;
  parent: string;
}

export interface DataTextResp {
  name: string;
  path: string;
  size: number;
  mime?: string;
  kind?: MediaKind;
  suffix?: string;
  is_text: boolean;
  content: string;
  truncated: boolean;
  encoding?: string;
}

export interface LoginSessionResp {
  token: string;
  expires_in?: number;
  readonly_token?: string;
  readonly_expires_in?: number;
  data_token?: string;
  data_expires_in?: number;
  base_url?: string;
}

export interface LoginChallengeResp {
  challenge: "totp";
  challenge_token: string;
  expires_in: number;
  issuer?: string;
  account?: string;
}

export type LoginResp = LoginSessionResp | LoginChallengeResp;

export interface PortalConfig {
  access_urls: string[];
  public_base_url: string;
  expose_astrbot_data: boolean;
  max_file_size_mb: number;
  max_file_size_bytes: number;
  trash_retention_days?: number;
  readonly_token?: string;
  data_token?: string;
  totp_feature_enabled?: boolean;
  totp_active?: boolean;
}

export interface TotpStatus {
  feature_enabled: boolean;
  enabled: boolean;
  issuer: string;
  account: string;
  enrolled_at: number;
  last_used_at: number;
  remaining_recovery_codes: number;
  pending_setup: boolean;
}

export interface TotpSetupResp {
  secret: string;
  otpauth_uri: string;
  qrcode_svg: string;
  issuer: string;
  account: string;
  expires_in: number;
}

export interface TotpConfirmResp {
  enabled: boolean;
  recovery_codes: string[];
  remaining_recovery_codes: number;
}

export interface TotpRegenerateResp {
  recovery_codes: string[];
  remaining_recovery_codes: number;
}

export interface TrashItem {
  id: number;
  original_media_id: number;
  category: string;
  filename: string;
  original_rel_path: string;
  trash_rel_path: string;
  abs_path: string;
  kind: MediaKind;
  mime: string;
  size: number;
  size_human?: string;
  sha256: string;
  source_url?: string;
  sender_id?: string;
  description?: string;
  tags?: string[];
  created_at?: number;
  updated_at?: number;
  deleted_at?: number;
  duration?: number;
  expires_at?: number;
  remaining_days?: number;
}

export interface TrashListResp {
  items: TrashItem[];
  total: number;
  total_pages: number;
  page: number;
  page_size: number;
}

export interface TrashStatsResp {
  total_count: number;
  total_size: number;
  total_size_human: string;
  expired_count: number;
  retention_days: number;
}

export interface DuplicateGroup {
  group_key: string;
  reason: string;
  confidence: "exact" | "suspect" | string;
  count: number;
  items: MediaItem[];
}

export interface DuplicateGroupsResp {
  items: DuplicateGroup[];
  total: number;
  total_pages: number;
  page: number;
  page_size: number;
  mode: string;
}

export interface UploadResp {
  saved?: Array<Record<string, any>>;
  errors?: string[];
}

export interface SaveUrlPayload {
  category: string;
  description?: string;
  url: string;
  filename?: string;
  duplicate_policy?: "error" | "force" | "reuse" | string;
}

export type ToastType = "success" | "error" | "info" | "warning";

export interface ToastMessage {
  id: string;
  text: string;
  type: ToastType;
  title: string;
}

export interface ConfirmOptions {
  title?: string;
  message?: string;
  detail?: string;
  confirmText?: string;
  cancelText?: string;
  tone?: "danger" | "warning" | "primary" | "info" | "success";
  icon?: string;
}

export interface ContextMenuEntry {
  key?: string;
  icon?: string;
  label?: string;
  tone?: string;
  disabled?: boolean;
  divider?: boolean;
  shortcut?: string;
}

export interface UploadJob {
  id: string;
  name: string;
  size: number;
  category: string;
  description: string;
  progress: number;
  loaded: number;
  status: "uploading" | "done" | "error" | "cancelled";
  message: string;
  xhr: XMLHttpRequest | null;
}
