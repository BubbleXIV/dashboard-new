import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { insertAttendanceEventSchema } from "@shared/schema";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Plus, Edit } from "lucide-react";
import { z } from "zod";
import type { Guild, AttendanceEvent } from "@shared/schema";

interface AttendanceProps {
  guild: Guild;
}

const attendanceEventFormSchema = insertAttendanceEventSchema.extend({
  dateString: z.string().min(1, "Date is required"),
  timeString: z.string().min(1, "Time is required"),
}).omit({ date: true });

type AttendanceEventFormData = z.infer<typeof attendanceEventFormSchema>;

export default function Attendance({ guild }: AttendanceProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const { data: events = [], isLoading } = useQuery<AttendanceEvent[]>({
    queryKey: ['/api/guilds', guild.id, 'attendance'],
  });

  const createEventMutation = useMutation({
    mutationFn: (data: AttendanceEventFormData) => {
      const { dateString, timeString, ...eventData } = data;
      const combinedDateTime = new Date(`${dateString}T${timeString}`);
      
      return apiRequest('POST', `/api/guilds/${guild.id}/attendance`, {
        ...eventData,
        date: combinedDateTime.toISOString(),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'attendance'] });
      setIsCreateModalOpen(false);
      toast({
        title: "Event created",
        description: "The attendance event has been created successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to create attendance event.",
        variant: "destructive",
      });
    },
  });

  const form = useForm<AttendanceEventFormData>({
    resolver: zodResolver(attendanceEventFormSchema),
    defaultValues: {
      name: "",
      description: "",
      dateString: "",
      timeString: "",
      isRecurring: false,
      roles: [],
      attendees: [],
      channelId: "",
      messageId: "",
    },
  });

  const onSubmit = (data: AttendanceEventFormData) => {
    createEventMutation.mutate(data);
  };

  const getProgressColor = (current: number, required: number) => {
    const percentage = (current / required) * 100;
    if (percentage >= 100) return "bg-discord-success";
    if (percentage >= 50) return "bg-discord-warning";
    return "bg-discord-blurple";
  };

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
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Attendance Management</h2>
        <p className="text-discord-text-secondary">Create and manage events with attendance tracking</p>
      </div>
      
      <div className="mb-6">
        <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
          <DialogTrigger asChild>
            <Button 
              className="bg-discord-blurple hover:bg-discord-dark-blurple"
              data-testid="button-create-event"
            >
              <Plus className="h-4 w-4 mr-2" />
              Create Event
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-discord-secondary border-discord-tertiary max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-discord-text">Create New Event</DialogTitle>
            </DialogHeader>
            
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Event Title</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="Enter event title" 
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
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Description</FormLabel>
                      <FormControl>
                        <Textarea 
                          placeholder="Event description" 
                          className="bg-discord-tertiary border-discord-bg text-discord-text resize-none"
                          rows={3}
                          {...field} 
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="dateString"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-discord-text">Date</FormLabel>
                        <FormControl>
                          <Input 
                            type="date" 
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
                    name="timeString"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-discord-text">Time</FormLabel>
                        <FormControl>
                          <Input 
                            type="time" 
                            className="bg-discord-tertiary border-discord-bg text-discord-text"
                            {...field} 
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="isRecurring"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between">
                      <FormLabel className="text-discord-text">Recurring Event</FormLabel>
                      <FormControl>
                        <Switch 
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <div className="flex gap-3 pt-4">
                  <Button 
                    type="button" 
                    variant="outline" 
                    onClick={() => setIsCreateModalOpen(false)}
                    className="flex-1 bg-discord-tertiary border-discord-bg text-discord-text hover:bg-discord-bg"
                  >
                    Cancel
                  </Button>
                  <Button 
                    type="submit" 
                    className="flex-1 bg-discord-blurple hover:bg-discord-dark-blurple"
                    disabled={createEventMutation.isPending}
                    data-testid="button-submit-event"
                  >
                    {createEventMutation.isPending ? "Creating..." : "Create Event"}
                  </Button>
                </div>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>
      
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {events.length === 0 ? (
          <div className="col-span-full text-center py-8 text-discord-text-muted">
            <p>No attendance events found</p>
            <p className="text-sm mt-1">Create your first event to get started</p>
          </div>
        ) : (
          events.map((event) => (
            <Card key={event.id} className="bg-discord-secondary border-discord-tertiary">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg font-semibold mb-1 text-discord-text">
                      {event.name}
                    </CardTitle>
                    <p className="text-discord-text-secondary text-sm">
                      {new Date(event.date).toLocaleDateString()} at {new Date(event.date).toLocaleTimeString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge 
                      variant={event.isRecurring ? "default" : "secondary"}
                      className={event.isRecurring ? "bg-discord-success" : "bg-discord-text-muted"}
                    >
                      {event.isRecurring ? "Recurring" : "One-time"}
                    </Badge>
                    <Button 
                      variant="ghost" 
                      size="sm"
                      className="text-discord-text-secondary hover:text-discord-text"
                      data-testid={`button-edit-event-${event.id}`}
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent>
                {event.description && (
                  <p className="text-sm text-discord-text-secondary mb-4">{event.description}</p>
                )}
                
                <div className="space-y-3 mb-4">
                  {event.roles.map((role, index) => {
                    const progress = role.required > 0 ? (role.current / role.required) * 100 : 0;
                    return (
                      <div key={index} className="flex items-center justify-between">
                        <span className="text-sm text-discord-text-secondary">
                          {role.name} ({role.current}/{role.required})
                        </span>
                        <div className="w-24">
                          <Progress 
                            value={progress} 
                            className="h-2 bg-discord-tertiary"
                          />
                        </div>
                      </div>
                    );
                  })}
                  
                  {event.roles.length === 0 && (
                    <div className="text-sm text-discord-text-muted">
                      No specific roles required
                    </div>
                  )}
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-discord-text">
                    {event.attendees.length} attendees
                  </span>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    className="text-discord-blurple hover:text-blue-400"
                    data-testid={`button-view-attendees-${event.id}`}
                  >
                    View Details
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
