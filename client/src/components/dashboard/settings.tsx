import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Save } from "lucide-react";
import { z } from "zod";
import type { Guild } from "@shared/schema";

interface SettingsProps {
  guild: Guild;
}

const settingsSchema = z.object({
  prefix: z.string().min(1, "Prefix is required").max(5, "Prefix must be 5 characters or less"),
  autoDelete: z.boolean(),
  dmResponses: z.boolean(),
  logChannel: z.string().optional(),
  logging: z.object({
    memberEvents: z.boolean(),
    messageEvents: z.boolean(),
    roleEvents: z.boolean(),
  }),
});

type SettingsFormData = z.infer<typeof settingsSchema>;

export default function Settings({ guild }: SettingsProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: currentGuild } = useQuery<Guild>({
    queryKey: ['/api/guilds', guild.id],
    initialData: guild,
  });

  const updateSettingsMutation = useMutation({
    mutationFn: (data: SettingsFormData) => 
      apiRequest('PATCH', `/api/guilds/${guild.id}`, { 
        settings: data 
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id] });
      toast({
        title: "Settings saved",
        description: "Bot settings have been updated successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to save settings.",
        variant: "destructive",
      });
    },
  });

  const form = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      prefix: currentGuild?.settings?.prefix || "!",
      autoDelete: currentGuild?.settings?.autoDelete || false,
      dmResponses: currentGuild?.settings?.dmResponses || false,
      logChannel: currentGuild?.settings?.logChannel || "",
      logging: {
        memberEvents: currentGuild?.settings?.logging?.memberEvents || false,
        messageEvents: currentGuild?.settings?.logging?.messageEvents || false,
        roleEvents: currentGuild?.settings?.logging?.roleEvents || false,
      },
    },
  });

  const onSubmit = (data: SettingsFormData) => {
    updateSettingsMutation.mutate(data);
  };

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Bot Settings</h2>
        <p className="text-discord-text-secondary">Configure general bot behavior and preferences</p>
      </div>
      
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* General Settings */}
            <Card className="bg-discord-secondary border-discord-tertiary">
              <CardHeader>
                <CardTitle className="text-lg font-semibold text-discord-text">General Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="prefix"
                  render={({ field }) => (
                    <FormItem>
                      <div className="flex items-center justify-between">
                        <div>
                          <FormLabel className="text-discord-text font-medium">Bot Prefix</FormLabel>
                          <p className="text-sm text-discord-text-secondary">Command prefix for the bot</p>
                        </div>
                        <FormControl>
                          <Input 
                            className="bg-discord-tertiary border-discord-bg text-discord-text w-16 text-center"
                            {...field} 
                          />
                        </FormControl>
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="autoDelete"
                  render={({ field }) => (
                    <FormItem>
                      <div className="flex items-center justify-between">
                        <div>
                          <FormLabel className="text-discord-text font-medium">Auto Delete Commands</FormLabel>
                          <p className="text-sm text-discord-text-secondary">Delete command messages after execution</p>
                        </div>
                        <FormControl>
                          <Switch 
                            checked={field.value}
                            onCheckedChange={field.onChange}
                            data-testid="switch-auto-delete"
                          />
                        </FormControl>
                      </div>
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="dmResponses"
                  render={({ field }) => (
                    <FormItem>
                      <div className="flex items-center justify-between">
                        <div>
                          <FormLabel className="text-discord-text font-medium">DM Responses</FormLabel>
                          <p className="text-sm text-discord-text-secondary">Send command responses via DM</p>
                        </div>
                        <FormControl>
                          <Switch 
                            checked={field.value}
                            onCheckedChange={field.onChange}
                            data-testid="switch-dm-responses"
                          />
                        </FormControl>
                      </div>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
            
            {/* Logging Settings */}
            <Card className="bg-discord-secondary border-discord-tertiary">
              <CardHeader>
                <CardTitle className="text-lg font-semibold text-discord-text">Logging Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="logChannel"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Log Channel</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger className="bg-discord-tertiary border-discord-bg text-discord-text">
                            <SelectValue placeholder="# Select channel" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent className="bg-discord-tertiary border-discord-bg">
                          <SelectItem value="123" className="text-discord-text"># mod-logs</SelectItem>
                          <SelectItem value="456" className="text-discord-text"># admin-logs</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <div className="space-y-3">
                  <FormField
                    control={form.control}
                    name="logging.memberEvents"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center justify-between">
                          <FormLabel className="text-sm text-discord-text">Member Join/Leave</FormLabel>
                          <FormControl>
                            <Switch 
                              checked={field.value}
                              onCheckedChange={field.onChange}
                              data-testid="switch-member-events"
                            />
                          </FormControl>
                        </div>
                      </FormItem>
                    )}
                  />
                  
                  <FormField
                    control={form.control}
                    name="logging.messageEvents"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center justify-between">
                          <FormLabel className="text-sm text-discord-text">Message Edits/Deletes</FormLabel>
                          <FormControl>
                            <Switch 
                              checked={field.value}
                              onCheckedChange={field.onChange}
                              data-testid="switch-message-events"
                            />
                          </FormControl>
                        </div>
                      </FormItem>
                    )}
                  />
                  
                  <FormField
                    control={form.control}
                    name="logging.roleEvents"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center justify-between">
                          <FormLabel className="text-sm text-discord-text">Role Changes</FormLabel>
                          <FormControl>
                            <Switch 
                              checked={field.value}
                              onCheckedChange={field.onChange}
                              data-testid="switch-role-events"
                            />
                          </FormControl>
                        </div>
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>
          </div>
          
          <div className="pt-6">
            <Button 
              type="submit" 
              className="bg-discord-success hover:bg-green-600"
              disabled={updateSettingsMutation.isPending}
              data-testid="button-save-settings"
            >
              <Save className="h-4 w-4 mr-2" />
              {updateSettingsMutation.isPending ? "Saving..." : "Save Settings"}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
