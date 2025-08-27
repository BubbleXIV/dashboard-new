import { useEffect } from "react";
import { useLocation } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { SiDiscord } from "react-icons/si";

export default function Login() {
  const [, setLocation] = useLocation();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      setLocation('/server-selection');
    }
  }, [isAuthenticated, setLocation]);

  const handleDiscordLogin = () => {
    window.location.href = '/api/auth/discord';
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-discord-blurple to-discord-dark-blurple">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-discord-blurple to-discord-dark-blurple">
      <Card className="w-full max-w-md mx-4 bg-discord-secondary border-discord-tertiary">
        <CardContent className="pt-6">
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-discord-blurple rounded-full flex items-center justify-center mx-auto mb-4">
              <SiDiscord className="text-2xl text-white" />
            </div>
            <h1 className="text-2xl font-bold mb-2 text-discord-text">Bot Dashboard</h1>
            <p className="text-discord-text-secondary">Manage your Discord bot settings</p>
          </div>
          
          <Button 
            onClick={handleDiscordLogin}
            className="w-full bg-discord-blurple hover:bg-discord-dark-blurple text-white"
            data-testid="button-login-discord"
          >
            <SiDiscord className="mr-3 h-4 w-4" />
            Login with Discord
          </Button>
          
          <div className="mt-6 text-center text-sm text-discord-text-muted">
            <p>By logging in, you agree to our Terms of Service</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
