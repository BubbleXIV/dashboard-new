import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { 
  Home, 
  Shield, 
  Calendar, 
  ClipboardList, 
  Gift, 
  Hash, 
  TvIcon as Twitch, 
  Settings 
} from "lucide-react";

type SectionType = 'overview' | 'roles' | 'attendance' | 'forms' | 'giveaways' | 'channels' | 'twitch' | 'settings';

interface SidebarProps {
  currentSection: SectionType;
  onSectionChange: (section: SectionType) => void;
  isOpen: boolean;
  onClose: () => void;
}

interface NavItem {
  key: SectionType;
  label: string;
  icon: React.ElementType;
}

const navItems: NavItem[] = [
  { key: 'overview', label: 'Overview', icon: Home },
];

const botFeatures: NavItem[] = [
  { key: 'roles', label: 'Roles & Autoroles', icon: Shield },
  { key: 'attendance', label: 'Attendance', icon: Calendar },
  { key: 'forms', label: 'Forms', icon: ClipboardList },
  { key: 'giveaways', label: 'Giveaways', icon: Gift },
  { key: 'channels', label: 'Channel Management', icon: Hash },
  { key: 'twitch', label: 'Twitch Notifications', icon: Twitch },
];

const settingsItems: NavItem[] = [
  { key: 'settings', label: 'Bot Settings', icon: Settings },
];

export default function Sidebar({ currentSection, onSectionChange, isOpen, onClose }: SidebarProps) {
  const handleSectionClick = (section: SectionType) => {
    onSectionChange(section);
    if (window.innerWidth < 1024) {
      onClose();
    }
  };

  const renderNavItem = (item: NavItem) => {
    const isActive = currentSection === item.key;
    const Icon = item.icon;
    
    return (
      <Button
        key={item.key}
        variant="ghost"
        className={cn(
          "w-full justify-start gap-3 px-3 py-2 h-auto transition-colors",
          isActive 
            ? "bg-discord-blurple/20 text-discord-text" 
            : "text-discord-text-secondary hover:text-discord-text hover:bg-discord-blurple/20"
        )}
        onClick={() => handleSectionClick(item.key)}
        data-testid={`nav-${item.key}`}
      >
        <Icon className="h-5 w-5" />
        <span>{item.label}</span>
      </Button>
    );
  };

  return (
    <aside 
      className={cn(
        "w-64 bg-discord-secondary border-r border-discord-tertiary min-h-screen fixed lg:static z-40 transform transition-transform duration-300",
        isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      )}
    >
      <nav className="p-4 space-y-2">
        {navItems.map(renderNavItem)}
        
        <div className="pt-4">
          <h3 className="text-xs font-semibold text-discord-text-muted uppercase tracking-wider mb-2 px-3">
            Bot Features
          </h3>
          {botFeatures.map(renderNavItem)}
        </div>
        
        <div className="pt-4">
          <h3 className="text-xs font-semibold text-discord-text-muted uppercase tracking-wider mb-2 px-3">
            Settings
          </h3>
          {settingsItems.map(renderNavItem)}
        </div>
      </nav>
    </aside>
  );
}
