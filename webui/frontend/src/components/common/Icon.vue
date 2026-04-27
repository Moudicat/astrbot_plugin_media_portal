<template>
  <component
    :is="resolved"
    v-if="resolved"
    class="icon"
    :width="size"
    :height="size"
    :stroke-width="strokeWidth"
    aria-hidden="true"
  />
  <svg
    v-else
    class="icon icon-missing"
    xmlns="http://www.w3.org/2000/svg"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import { computed, type Component } from "vue";
import {
  AlertCircle,
  AlertTriangle,
  AlignLeft,
  Ban,
  CheckCheck,
  CheckCircle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleAlert,
  CircleCheck,
  CircleX,
  ClipboardCopy,
  Clock,
  Copy,
  CornerUpLeft,
  Cpu,
  Database,
  Download,
  Eraser,
  ExternalLink,
  Eye,
  EyeOff,
  File,
  FileDown,
  FileQuestion,
  FileText,
  FileUp,
  FileWarning,
  Film,
  Folder,
  FolderInput,
  FolderOpen,
  FolderPlus,
  FolderTree,
  Globe,
  HelpCircle,
  Home,
  Image as ImageIcon,
  Info,
  KeyRound,
  Languages,
  Layers,
  LayoutGrid,
  Library,
  Link,
  Link2,
  List,
  Loader,
  Loader2,
  Lock,
  LogIn,
  LogOut,
  Menu,
  Moon,
  Music,
  Package,
  PackageOpen,
  Pause,
  Pencil,
  Play,
  QrCode,
  RefreshCw,
  RotateCcw,
  Save,
  ScanLine,
  Scissors,
  Search,
  SearchX,
  Settings,
  Settings2,
  Shield,
  ShieldCheck,
  ShieldOff,
  Sticker,
  Sun,
  TriangleAlert,
  Trash2,
  Upload,
  UploadCloud,
  User,
  Volume2,
  VolumeX,
  X,
  ZoomIn,
} from "lucide-vue-next";

interface Props {
  name: string;
  size?: number | string;
  strokeWidth?: number | string;
}

const props = withDefaults(defineProps<Props>(), {
  size: 18,
  strokeWidth: 1.75,
});

const REGISTRY: Record<string, Component> = {
  "alert-circle": AlertCircle,
  "alert-triangle": AlertTriangle,
  "align-left": AlignLeft,
  ban: Ban,
  check: Check,
  "check-check": CheckCheck,
  "check-circle": CheckCircle,
  "chevron-down": ChevronDown,
  "chevron-left": ChevronLeft,
  "chevron-right": ChevronRight,
  "chevron-up": ChevronUp,
  "circle-alert": CircleAlert,
  "circle-check": CircleCheck,
  "circle-x": CircleX,
  "clipboard-copy": ClipboardCopy,
  clock: Clock,
  copy: Copy,
  "corner-up-left": CornerUpLeft,
  cpu: Cpu,
  database: Database,
  download: Download,
  eraser: Eraser,
  "external-link": ExternalLink,
  eye: Eye,
  "eye-off": EyeOff,
  file: File,
  "file-down": FileDown,
  "file-question": FileQuestion,
  "file-text": FileText,
  "file-up": FileUp,
  "file-warning": FileWarning,
  film: Film,
  folder: Folder,
  "folder-input": FolderInput,
  "folder-open": FolderOpen,
  "folder-plus": FolderPlus,
  "folder-tree": FolderTree,
  globe: Globe,
  "help-circle": HelpCircle,
  home: Home,
  image: ImageIcon,
  info: Info,
  "key-round": KeyRound,
  languages: Languages,
  layers: Layers,
  "layout-grid": LayoutGrid,
  library: Library,
  link: Link,
  "link-2": Link2,
  list: List,
  loader: Loader,
  "loader-2": Loader2,
  lock: Lock,
  "log-in": LogIn,
  "log-out": LogOut,
  menu: Menu,
  moon: Moon,
  music: Music,
  package: Package,
  "package-open": PackageOpen,
  pause: Pause,
  pencil: Pencil,
  play: Play,
  "qr-code": QrCode,
  "refresh-cw": RefreshCw,
  "rotate-ccw": RotateCcw,
  save: Save,
  "scan-line": ScanLine,
  scissors: Scissors,
  search: Search,
  "search-x": SearchX,
  settings: Settings,
  "settings-2": Settings2,
  shield: Shield,
  "shield-check": ShieldCheck,
  "shield-off": ShieldOff,
  sticker: Sticker,
  sun: Sun,
  "triangle-alert": TriangleAlert,
  trash: Trash2,
  "trash-2": Trash2,
  upload: Upload,
  "upload-cloud": UploadCloud,
  user: User,
  "volume-2": Volume2,
  "volume-x": VolumeX,
  x: X,
  "zoom-in": ZoomIn,
};

const resolved = computed<Component | null>(() => REGISTRY[props.name] || null);
</script>
