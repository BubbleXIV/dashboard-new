import { useEffect } from "react";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { getDiscordGuildIconUrl, formatMemberCount } from "@/lib/discord";
import { ChevronRight } from "lucide-react";
import type { Guild } from "@shared/schema";

export default function ServerSelection() {
  const [, setLocation] = useLocation();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const { data: guilds, isLoading } = useQuery<Guild[]>({
    queryKey: ['/api/guilds'],
    enabled: isAuthenticated,
  });

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      setLocation('/login');
    }
  }, [isAuthenticated, authLoading, setLocation]);

  const handleSelectServer = (guildId: string) => {
    setLocation(`/dashboard/${guildId}`);
  };

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-discord-bg">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-discord-blurple"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-discord-bg">
      <Card className="w-full max-w-2xl mx-4 bg-discord-secondary border-discord-tertiary">
        <CardContent className="p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold mb-2 text-discord-text">Select a Server</h1>
            <p className="text-discord-text-secondary">Choose a server where you have administrator permissions</p>
          </div>
          
          <div className="grid gap-4 max-h-96 overflow-y-auto">
            {guilds?.length === 0 && (
              <div className="text-center py-8 text-discord-text-muted">
                <p>No servers found where you have administrator permissions.</p>
                <p className="text-sm mt-2">Make sure the bot is invited to your server.</p>
              </div>
            )}
            
            {guilds?.map((guild) => (
              <Button
                key={guild.id}
                variant="ghost"
                className="bg-discord-tertiary hover:bg-discord-blurple/20 p-4 h-auto justify-start transition-colors duration-200"
                onClick={() => handleSelectServer(guild.id)}
                data-testid={`button-select-guild-${guild.id}`}
              >
                <div className="flex items-center gap-4 w-full">
                  {/* Server icon */}
                  <div className="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold bg-discord-blurple text-white">
                    {guild.icon ? (
                      <img 
                        src={getDiscordGuildIconUrl(guild.discordId, guild.icon)} 
                        alt={guild.name}
                        className="w-12 h-12 rounded-full"
                      />
                    ) : (
                      guild.name.charAt(0).toUpperCase()
                    )}
                  </div>
                  
                  <div className="flex-1 text-left">
                    <h3 className="font-medium text-discord-text">{guild.name}</h3>
                    <p className="text-sm text-discord-text-secondary">
                      {guild.ownerDiscordId ? 'Owner' : 'Administrator'} • {formatMemberCount(guild.memberCount)} members
                    </p>
                  </div>
                  
                  <ChevronRight className="h-5 w-5 text-discord-text-muted" />
                </div>
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
