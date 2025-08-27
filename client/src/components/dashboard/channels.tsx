import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useToast } from "@/hooks/use-toast";
import { Settings, Plus, Edit, Clock } from "lucide-react";
import { z } from "zod";
import type { Guild } from "@shared/schema";

interface ChannelsProps {
  guild: Guild;
}

const timezoneFormSchema = z.object({
  timezone: z.string().min(1, "Timezone is required"),
  channelName: z.string().min(1, "Channel name is required"),
});

type TimezoneFormData = z.infer<typeof timezoneFormSchema>;

const TIMEZONES = [
  { value: "America/Los_Angeles", label: "Pacific (PST/PDT)", display: "Pacific" },
  { value: "America/Denver", label: "Mountain (MST/MDT)", display: "Mountain" },
  { value: "America/Chicago", label: "Central (CST/CDT)", display: "Central" },
  { value: "America/New_York", label: "Eastern (EST/EDT)", display: "Eastern" },
  { value: "Europe/London", label: "Greenwich Mean Time (GMT)", display: "GMT" },
  { value: "Asia/Kolkata", label: "India Standard Time (IST)", display: "Indian" },
  { value: "Australia/Adelaide", label: "Australian Central (ACST)", display: "Australian Central" },
];

export default function Channels({ guild }: ChannelsProps) {
  const { toast } = useToast();
  const [isTimezoneModalOpen, setIsTimezoneModalOpen] = useState(false);
  const [mediaChannels, setMediaChannels] = useState([
    { id: "1", name: "#memes", description: "Images and GIFs only", enabled: true },
    { id: "2", name: "#screenshots", description: "Game screenshots", enabled: false },
  ]);
  const [timezoneChannels, setTimezoneChannels] = useState([
    { id: "1", timezone: "America/New_York", display: "Eastern", channelName: "🕒 3:45 PM Eastern" },
    { id: "2", timezone: "America/Los_Angeles", display: "Pacific", channelName: "🕒 12:45 PM Pacific" },
  ]);

  const timezoneForm = useForm<TimezoneFormData>({
    resolver: zodResolver(timezoneFormSchema),
    defaultValues: {
      timezone: "",
      channelName: "",
    },
  });

  const onSubmitTimezone = (data: TimezoneFormData) => {
    const selectedTz = TIMEZONES.find(tz => tz.value === data.timezone);
    if (!selectedTz) return;

    const newChannel = {
      id: Date.now().toString(),
      timezone: data.timezone,
      display: selectedTz.display,
      channelName: data.channelName,
    };

    setTimezoneChannels(prev => [...prev, newChannel]);
    setIsTimezoneModalOpen(false);
    timezoneForm.reset();
    
    toast({
      title: "Timezone channel added",
      description: "The timezone channel has been configured successfully.",
    });
  };

  const handleMediaChannelToggle = (channelId: string, enabled: boolean) => {
    setMediaChannels(prev => 
      prev.map(channel => 
        channel.id === channelId ? { ...channel, enabled } : channel
      )
    );
    
    toast({
      title: enabled ? "Media channel enabled" : "Media channel disabled",
      description: `Media filtering has been ${enabled ? 'enabled' : 'disabled'} for this channel.`,
    });
  };

  const handleRemoveTimezoneChannel = (channelId: string) => {
    setTimezoneChannels(prev => prev.filter(channel => channel.id !== channelId));
    toast({
      title: "Timezone channel removed",
      description: "The timezone channel has been removed successfully.",
    });
  };

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Channel Management</h2>
        <p className="text-discord-text-secondary">Configure specialized channel features</p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Media Channels */}
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-discord-text">Media Channels</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 mb-4">
              {mediaChannels.map((channel) => (
                <div key={channel.id} className="flex items-center justify-between p-3 bg-discord-tertiary rounded-lg">
                  <div>
                    <h4 className="font-medium text-discord-text">{channel.name}</h4>
                    <p className="text-sm text-discord-text-secondary">{channel.description}</p>
                  </div>
                  <Switch 
                    checked={channel.enabled}
                    onCheckedChange={(enabled) => handleMediaChannelToggle(channel.id, enabled)}
                    data-testid={`switch-media-channel-${channel.id}`}
                  />
                </div>
              ))}
            </div>
            
            <Button 
              className="w-full bg-discord-blurple hover:bg-discord-dark-blurple"
              data-testid="button-configure-media-channels"
            >
              Configure Media Channels
            </Button>
          </CardContent>
        </Card>
        
        {/* Temporary Channels */}
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-discord-text">Temporary Channels</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 mb-4">
              <div className="p-3 bg-discord-tertiary rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-medium text-discord-text">Create Voice Channel</h4>
                  <span className="text-xs bg-discord-success px-2 py-1 rounded text-white">Active</span>
                </div>
                <p className="text-sm text-discord-text-secondary">
                  Click to create temporary voice channels
                </p>
              </div>
              
              <div className="space-y-2">
                <h5 className="text-sm font-medium text-discord-text-secondary">Active Temporary Channels</h5>
                <div className="text-sm text-discord-text-muted">User's Room • 3 members</div>
                <div className="text-sm text-discord-text-muted">Study Group • 2 members</div>
              </div>
            </div>
            
            <Button 
              className="w-full bg-discord-success hover:bg-green-600"
              data-testid="button-configure-temp-channels"
            >
              Configure Temp Channels
            </Button>
          </CardContent>
        </Card>
        
        {/* Timezone Channels */}
        <Card className="bg-discord-secondary border-discord-tertiary lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
            <CardTitle className="text-lg font-semibold text-discord-text">Timezone Channels</CardTitle>
            <Dialog open={isTimezoneModalOpen} onOpenChange={setIsTimezoneModalOpen}>
              <DialogTrigger asChild>
                <Button 
                  className="bg-discord-warning hover:bg-yellow-600"
                  size="sm"
                  data-testid="button-add-timezone-channel"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Timezone Channel
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-discord-secondary border-discord-tertiary max-w-md">
                <DialogHeader>
                  <DialogTitle className="text-discord-text">Add Timezone Channel</DialogTitle>
                </DialogHeader>
                
                <Form {...timezoneForm}>
                  <form onSubmit={timezoneForm.handleSubmit(onSubmitTimezone)} className="space-y-4">
                    <FormField
                      control={timezoneForm.control}
                      name="timezone"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-discord-text">Timezone</FormLabel>
                          <Select onValueChange={field.onChange} defaultValue={field.value}>
                            <FormControl>
                              <SelectTrigger className="bg-discord-tertiary border-discord-bg text-discord-text">
                                <SelectValue placeholder="Select timezone" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent className="bg-discord-tertiary border-discord-bg">
                              {TIMEZONES.map((tz) => (
                                <SelectItem key={tz.value} value={tz.value} className="text-discord-text">
                                  {tz.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={timezoneForm.control}
                      name="channelName"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-discord-text">Channel Name</FormLabel>
                          <FormControl>
                            <Input 
                              placeholder="🕒 Time Display Name" 
                              className="bg-discord-tertiary border-discord-bg text-discord-text"
                              {...field} 
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="flex gap-3 pt-4">
                      <Button 
                        type="button" 
                        variant="outline" 
                        onClick={() => setIsTimezoneModalOpen(false)}
                        className="flex-1 bg-discord-tertiary border-discord-bg text-discord-text hover:bg-discord-bg"
                      >
                        Cancel
                      </Button>
                      <Button 
                        type="submit" 
                        className="flex-1 bg-discord-warning hover:bg-yellow-600"
                        data-testid="button-submit-timezone"
                      >
                        Add Channel
                      </Button>
                    </div>
                  </form>
                </Form>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {timezoneChannels.length === 0 ? (
                <div className="col-span-full text-center py-8 text-discord-text-muted">
                  <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p>No timezone channels configured</p>
                  <p className="text-sm mt-1">Add timezone channels to display current time</p>
                </div>
              ) : (
                timezoneChannels.map((channel) => (
                  <div key={channel.id} className="flex items-center justify-between p-3 bg-discord-tertiary rounded-lg">
                    <div>
                      <h4 className="font-medium text-discord-text">{channel.channelName}</h4>
                      <p className="text-sm text-discord-text-secondary">{channel.display} timezone display</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button 
                        variant="ghost" 
                        size="sm"
                        className="text-discord-text-secondary hover:text-discord-text"
                        data-testid={`button-edit-timezone-${channel.id}`}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button 
                        variant="ghost" 
                        size="sm"
                        className="text-discord-danger hover:text-red-400"
                        onClick={() => handleRemoveTimezoneChannel(channel.id)}
                        data-testid={`button-remove-timezone-${channel.id}`}
                      >
                        <Settings className="h-4 w-4" />
                      </Button>
                    </div>
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
