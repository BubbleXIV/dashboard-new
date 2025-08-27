import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { insertTwitchStreamerSchema } from "@shared/schema";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { SiTwitch } from "react-icons/si";
import { Trash2 } from "lucide-react";
import { z } from "zod";
import type { Guild, TwitchStreamer } from "@shared/schema";

interface TwitchProps {
  guild: Guild;
}

const twitchFormSchema = insertTwitchStreamerSchema.omit({});

type TwitchFormData = z.infer<typeof twitchFormSchema>;

export default function Twitch({ guild }: TwitchProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: streamers = [], isLoading } = useQuery<TwitchStreamer[]>({
    queryKey: ['/api/guilds', guild.id, 'twitch'],
  });

  const addStreamerMutation = useMutation({
    mutationFn: (data: TwitchFormData) => apiRequest('POST', `/api/guilds/${guild.id}/twitch`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'twitch'] });
      form.reset();
      toast({
        title: "Streamer added",
        description: "The Twitch streamer has been added successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to add Twitch streamer.",
        variant: "destructive",
      });
    },
  });

  const removeStreamerMutation = useMutation({
    mutationFn: (streamerId: string) => apiRequest('DELETE', `/api/twitch/${streamerId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'twitch'] });
      toast({
        title: "Streamer removed",
        description: "The Twitch streamer has been removed successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to remove Twitch streamer.",
        variant: "destructive",
      });
    },
  });

  const form = useForm<TwitchFormData>({
    resolver: zodResolver(twitchFormSchema),
    defaultValues: {
      username: "",
      isLive: false,
      viewerCount: 0,
      gameName: "",
      streamTitle: "",
      notificationChannelId: "",
    },
  });

  const onSubmit = (data: TwitchFormData) => {
    addStreamerMutation.mutate(data);
  };

  const handleRemoveStreamer = (streamerId: string) => {
    if (window.confirm("Are you sure you want to remove this streamer?")) {
      removeStreamerMutation.mutate(streamerId);
    }
  };

  const liveStreamers = streamers.filter(s => s.isLive);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-discord-blurple"></div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Twitch Notifications</h2>
        <p className="text-discord-text-secondary">Monitor streamers and send live notifications</p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-3 h-3 bg-discord-success rounded-full animate-pulse"></div>
              <h3 className="text-lg font-semibold text-discord-text">{liveStreamers.length} Live</h3>
            </div>
            <p className="text-discord-text-secondary">Currently streaming</p>
          </CardContent>
        </Card>
        
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold mb-2 text-discord-text">{streamers.length} Total</h3>
            <p className="text-discord-text-secondary">Monitored streamers</p>
          </CardContent>
        </Card>
        
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold mb-2 text-discord-text">#live-streams</h3>
            <p className="text-discord-text-secondary">Notification channel</p>
          </CardContent>
        </Card>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Add Streamer */}
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-discord-text">Add Streamer</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="username"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Twitch Username</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="Enter Twitch username" 
                          className="bg-discord-tertiary border-discord-bg text-discord-text"
                          {...field} 
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="notificationChannelId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Notification Channel</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value || ""}>
                        <FormControl>
                          <SelectTrigger className="bg-discord-tertiary border-discord-bg text-discord-text">
                            <SelectValue placeholder="# Select channel" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent className="bg-discord-tertiary border-discord-bg">
                          <SelectItem value="123" className="text-discord-text"># live-streams</SelectItem>
                          <SelectItem value="456" className="text-discord-text"># announcements</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <Button 
                  type="submit" 
                  className="w-full bg-purple-600 hover:bg-purple-700"
                  disabled={addStreamerMutation.isPending}
                  data-testid="button-add-streamer"
                >
                  <SiTwitch className="h-4 w-4 mr-2" />
                  {addStreamerMutation.isPending ? "Adding..." : "Add Streamer"}
                </Button>
              </form>
            </Form>
          </CardContent>
        </Card>
        
        {/* Streamers List */}
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-discord-text">Monitored Streamers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {streamers.length === 0 ? (
                <div className="text-center py-8 text-discord-text-muted">
                  <SiTwitch className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p>No streamers added</p>
                  <p className="text-sm mt-1">Add your first streamer to get started</p>
                </div>
              ) : (
                streamers.map((streamer) => (
                  <div key={streamer.id} className="flex items-center justify-between p-3 bg-discord-tertiary rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${
                        streamer.isLive ? 'bg-discord-success animate-pulse' : 'bg-discord-text-muted'
                      }`}></div>
                      <div>
                        <h4 className="font-medium text-discord-text">{streamer.username}</h4>
                        <p className="text-sm text-discord-text-secondary">
                          {streamer.isLive 
                            ? `Playing ${streamer.gameName || 'Unknown'} • ${streamer.viewerCount} viewers`
                            : 'Offline'
                          }
                        </p>
                      </div>
                    </div>
                    <Button 
                      variant="ghost" 
                      size="sm"
                      className="text-discord-danger hover:text-red-400"
                      onClick={() => handleRemoveStreamer(streamer.id)}
                      data-testid={`button-remove-streamer-${streamer.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
