import { useEffect, useState } from "react";
import { useParams, useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import Header from "@/components/dashboard/header";
import Sidebar from "@/components/dashboard/sidebar";
import Overview from "@/components/dashboard/overview";
import Roles from "@/components/dashboard/roles";
import Attendance from "@/components/dashboard/attendance";
import Forms from "@/components/dashboard/forms";
import Giveaways from "@/components/dashboard/giveaways";
import Channels from "@/components/dashboard/channels";
import Twitch from "@/components/dashboard/twitch";
import Settings from "@/components/dashboard/settings";
import type { Guild } from "@shared/schema";

type SectionType = 'overview' | 'roles' | 'attendance' | 'forms' | 'giveaways' | 'channels' | 'twitch' | 'settings';

export default function Dashboard() {
  const { guildId } = useParams<{ guildId: string }>();
  const [, setLocation] = useLocation();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [currentSection, setCurrentSection] = useState<SectionType>('overview');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const { data: guild, isLoading } = useQuery<Guild>({
    queryKey: ['/api/guilds', guildId],
    enabled: isAuthenticated && !!guildId,
  });

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      setLocation('/login');
    }
  }, [isAuthenticated, authLoading, setLocation]);

  useEffect(() => {
    if (!guildId && isAuthenticated) {
      setLocation('/server-selection');
    }
  }, [guildId, isAuthenticated, setLocation]);

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const renderSection = () => {
    if (!guild) return null;

    switch (currentSection) {
      case 'overview':
        return <Overview guild={guild} />;
      case 'roles':
        return <Roles guild={guild} />;
      case 'attendance':
        return <Attendance guild={guild} />;
      case 'forms':
        return <Forms guild={guild} />;
      case 'giveaways':
        return <Giveaways guild={guild} />;
      case 'channels':
        return <Channels guild={guild} />;
      case 'twitch':
        return <Twitch guild={guild} />;
      case 'settings':
        return <Settings guild={guild} />;
      default:
        return <Overview guild={guild} />;
    }
  };

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-discord-bg">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-discord-blurple"></div>
      </div>
    );
  }

  if (!guild) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-discord-bg">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-discord-text mb-2">Guild not found</h1>
          <p className="text-discord-text-secondary">The selected server could not be found or you don't have access to it.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-discord-bg">
      <Header 
        guild={guild} 
        onToggleSidebar={toggleSidebar}
      />
      
      <div className="flex">
        <Sidebar 
          currentSection={currentSection}
          onSectionChange={setCurrentSection}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
        
        <main className="flex-1 p-6 lg:ml-0">
          {renderSection()}
        </main>
      </div>
      
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-30 lg:hidden" 
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}
