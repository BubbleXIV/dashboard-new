import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { getDiscordGuildIconUrl, getDiscordAvatarUrl } from "@/lib/discord";
import { Menu, ChevronDown } from "lucide-react";
import { SiDiscord } from "react-icons/si";
import type { Guild } from "@shared/schema";

interface HeaderProps {
  guild: Guild;
  onToggleSidebar: () => void;
}

export default function Header({ guild, onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuth();

  return (
    <header className="bg-discord-secondary border-b border-discord-tertiary px-6 py-4 sticky top-0 z-50">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden text-discord-text-secondary hover:text-discord-text"
            onClick={onToggleSidebar}
            data-testid="button-toggle-sidebar"
          >
            <Menu className="h-5 w-5" />
          </Button>
          
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-discord-blurple rounded-full flex items-center justify-center">
              <SiDiscord className="text-sm text-white" />
            </div>
            <h1 className="text-xl font-bold text-discord-text">Bot Dashboard</h1>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {/* Server Selector */}
          <div className="relative">
            <Button
              variant="ghost"
              className="flex items-center gap-2 bg-discord-tertiary px-3 py-2 hover:bg-discord-blurple/20"
              data-testid="button-guild-selector"
            >
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-discord-blurple text-white">
                {guild.icon ? (
                  <img 
                    src={getDiscordGuildIconUrl(guild.discordId, guild.icon)} 
                    alt={guild.name}
                    className="w-6 h-6 rounded-full"
                  />
                ) : (
                  guild.name.charAt(0).toUpperCase()
                )}
              </div>
              <span className="hidden sm:block text-discord-text">{guild.name}</span>
              <ChevronDown className="h-3 w-3 text-discord-text-muted" />
            </Button>
          </div>
          
          {/* User Profile */}
          <div className="flex items-center gap-3">
            {/* Bot Status */}
            <div className="flex items-center gap-2 text-sm">
              <div className="w-2 h-2 bg-discord-success rounded-full animate-pulse"></div>
              <span className="hidden sm:block text-discord-text-secondary">Online</span>
            </div>
            
            {/* User Avatar */}
            <Button
              variant="ghost"
              size="sm"
              className="p-0 h-8 w-8 rounded-full"
              onClick={logout}
              data-testid="button-user-menu"
            >
              {user?.avatar ? (
                <img 
                  src={getDiscordAvatarUrl(user.discordId, user.avatar)} 
                  alt={user.username}
                  className="w-8 h-8 rounded-full"
                />
              ) : (
                <div className="w-8 h-8 bg-discord-blurple rounded-full flex items-center justify-center">
                  <span className="text-sm text-white font-medium">
                    {user?.username?.charAt(0).toUpperCase()}
                  </span>
                </div>
              )}
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
