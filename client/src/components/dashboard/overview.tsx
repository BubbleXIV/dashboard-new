import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Users, Calendar, Shield, TvIcon as Twitch } from "lucide-react";
import type { Guild } from "@shared/schema";
import { formatMemberCount } from "@/lib/discord";

interface OverviewProps {
  guild: Guild;
}

export default function Overview({ guild }: OverviewProps) {
  const { data: attendanceEvents = [] } = useQuery({
    queryKey: ['/api/guilds', guild.id, 'attendance'],
  });

  const { data: twitchStreamers = [] } = useQuery({
    queryKey: ['/api/guilds', guild.id, 'twitch'],
  });

  const liveStreamers = twitchStreamers.filter((s: any) => s.isLive);

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Dashboard Overview</h2>
        <p className="text-discord-text-secondary">Monitor your bot's activity and manage server features</p>
      </div>
      
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 mb-8">
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-discord-blurple/20 rounded-lg flex items-center justify-center">
                <Users className="text-discord-blurple text-xl h-6 w-6" />
              </div>
              <span className="text-discord-success text-sm font-medium">+12%</span>
            </div>
            <h3 className="text-2xl font-bold mb-1 text-discord-text" data-testid="stat-member-count">
              {formatMemberCount(guild.memberCount)}
            </h3>
            <p className="text-discord-text-secondary text-sm">Total Members</p>
          </CardContent>
        </Card>
        
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-discord-success/20 rounded-lg flex items-center justify-center">
                <Calendar className="text-discord-success text-xl h-6 w-6" />
              </div>
              <span className="text-discord-success text-sm font-medium">+{attendanceEvents.length}</span>
            </div>
            <h3 className="text-2xl font-bold mb-1 text-discord-text" data-testid="stat-active-events">
              {attendanceEvents.length}
            </h3>
            <p className="text-discord-text-secondary text-sm">Active Events</p>
          </CardContent>
        </Card>
        
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-discord-warning/20 rounded-lg flex items-center justify-center">
                <Shield className="text-discord-warning text-xl h-6 w-6" />
              </div>
              <span className="text-discord-text-muted text-sm font-medium">--</span>
            </div>
            <h3 className="text-2xl font-bold mb-1 text-discord-text" data-testid="stat-auto-roles">
              0
            </h3>
            <p className="text-discord-text-secondary text-sm">Auto Roles</p>
          </CardContent>
        </Card>
        
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 bg-purple-500/20 rounded-lg flex items-center justify-center">
                <Twitch className="text-purple-400 text-xl h-6 w-6" />
              </div>
              <span className="text-discord-success text-sm font-medium">{liveStreamers.length} live</span>
            </div>
            <h3 className="text-2xl font-bold mb-1 text-discord-text" data-testid="stat-twitch-streamers">
              {twitchStreamers.length}
            </h3>
            <p className="text-discord-text-secondary text-sm">Twitch Streamers</p>
          </CardContent>
        </Card>
      </div>
      
      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-discord-text">Recent Events</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {attendanceEvents.length === 0 ? (
              <div className="text-center py-8 text-discord-text-muted">
                <p>No recent events</p>
                <p className="text-sm mt-1">Create your first event to get started</p>
              </div>
            ) : (
              attendanceEvents.slice(0, 3).map((event: any) => (
                <div key={event.id} className="flex items-center gap-3 p-3 bg-discord-tertiary rounded-lg">
                  <div className="w-10 h-10 bg-discord-blurple rounded-lg flex items-center justify-center">
                    <Calendar className="h-5 w-5 text-white" />
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium text-discord-text">{event.name}</h4>
                    <p className="text-sm text-discord-text-secondary">
                      {new Date(event.date).toLocaleDateString()} • {event.attendees?.length || 0} attending
                    </p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
        
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-discord-text">Bot Activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-discord-text-secondary">Commands Used Today</span>
              <span className="font-medium text-discord-text">0</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-discord-text-secondary">Auto Roles Assigned</span>
              <span className="font-medium text-discord-text">0</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-discord-text-secondary">Forms Submitted</span>
              <span className="font-medium text-discord-text">0</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-discord-text-secondary">Events Created</span>
              <span className="font-medium text-discord-text">{attendanceEvents.length}</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
