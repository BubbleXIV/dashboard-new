import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { insertGiveawaySchema } from "@shared/schema";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Plus, Gift } from "lucide-react";
import { z } from "zod";
import type { Guild, Giveaway } from "@shared/schema";

interface GiveawaysProps {
  guild: Guild;
}

const giveawayFormSchema = insertGiveawaySchema.extend({
  dateString: z.string().min(1, "Date is required"),
  timeString: z.string().min(1, "Time is required"),
}).omit({ endsAt: true });

type GiveawayFormData = z.infer<typeof giveawayFormSchema>;

export default function Giveaways({ guild }: GiveawaysProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const { data: giveaways = [], isLoading } = useQuery<Giveaway[]>({
    queryKey: ['/api/guilds', guild.id, 'giveaways'],
  });

  const createGiveawayMutation = useMutation({
    mutationFn: (data: GiveawayFormData) => {
      const { dateString, timeString, ...giveawayData } = data;
      const combinedDateTime = new Date(`${dateString}T${timeString}`);
      
      return apiRequest('POST', `/api/guilds/${guild.id}/giveaways`, {
        ...giveawayData,
        endsAt: combinedDateTime.toISOString(),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'giveaways'] });
      setIsCreateModalOpen(false);
      toast({
        title: "Giveaway created",
        description: "The giveaway has been created successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to create giveaway.",
        variant: "destructive",
      });
    },
  });

  const endGiveawayMutation = useMutation({
    mutationFn: (giveawayId: string) => 
      apiRequest('PATCH', `/api/giveaways/${giveawayId}`, { isActive: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'giveaways'] });
      toast({
        title: "Giveaway ended",
        description: "The giveaway has been ended successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to end giveaway.",
        variant: "destructive",
      });
    },
  });

  const form = useForm<GiveawayFormData>({
    resolver: zodResolver(giveawayFormSchema),
    defaultValues: {
      title: "",
      description: "",
      prize: "",
      winnerCount: 1,
      dateString: "",
      timeString: "",
      entries: [],
      winners: [],
      channelId: "",
      messageId: "",
      isActive: true,
    },
  });

  const onSubmit = (data: GiveawayFormData) => {
    createGiveawayMutation.mutate(data);
  };

  const handleEndGiveaway = (giveawayId: string) => {
    if (window.confirm("Are you sure you want to end this giveaway?")) {
      endGiveawayMutation.mutate(giveawayId);
    }
  };

  const getTimeRemaining = (endsAt: Date | string) => {
    const now = new Date();
    const end = new Date(endsAt);
    const diff = end.getTime() - now.getTime();
    
    if (diff <= 0) return "Ended";
    
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    
    if (days > 0) return `${days} day${days > 1 ? 's' : ''}`;
    if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''}`;
    return "Less than 1 hour";
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
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Giveaway Management</h2>
        <p className="text-discord-text-secondary">Create and manage server giveaways</p>
      </div>
      
      <div className="mb-6">
        <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
          <DialogTrigger asChild>
            <Button 
              className="bg-discord-blurple hover:bg-discord-dark-blurple"
              data-testid="button-create-giveaway"
            >
              <Gift className="h-4 w-4 mr-2" />
              Create Giveaway
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-discord-secondary border-discord-tertiary max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-discord-text">Create New Giveaway</DialogTitle>
            </DialogHeader>
            
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="title"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Giveaway Title</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="Enter giveaway title" 
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
                  name="prize"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Prize</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="What are you giving away?" 
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
                          placeholder="Giveaway description" 
                          className="bg-discord-tertiary border-discord-bg text-discord-text resize-none"
                          rows={3}
                          {...field} 
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="winnerCount"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Number of Winners</FormLabel>
                      <FormControl>
                        <Input 
                          type="number" 
                          min="1"
                          className="bg-discord-tertiary border-discord-bg text-discord-text"
                          {...field}
                          onChange={(e) => field.onChange(parseInt(e.target.value) || 1)} 
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
                        <FormLabel className="text-discord-text">End Date</FormLabel>
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
                        <FormLabel className="text-discord-text">End Time</FormLabel>
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
                    disabled={createGiveawayMutation.isPending}
                    data-testid="button-submit-giveaway"
                  >
                    {createGiveawayMutation.isPending ? "Creating..." : "Create Giveaway"}
                  </Button>
                </div>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {giveaways.length === 0 ? (
          <div className="col-span-full text-center py-8 text-discord-text-muted">
            <p>No giveaways found</p>
            <p className="text-sm mt-1">Create your first giveaway to get started</p>
          </div>
        ) : (
          giveaways.map((giveaway) => {
            const isActive = giveaway.isActive && new Date(giveaway.endsAt) > new Date();
            const hasEnded = new Date(giveaway.endsAt) <= new Date();
            
            return (
              <Card key={giveaway.id} className="bg-discord-secondary border-discord-tertiary">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-lg font-semibold mb-1 text-discord-text">
                        {giveaway.title}
                      </CardTitle>
                      {giveaway.description && (
                        <p className="text-discord-text-secondary text-sm">{giveaway.description}</p>
                      )}
                    </div>
                    <Badge 
                      variant={isActive ? "default" : "secondary"}
                      className={isActive ? "bg-discord-success" : hasEnded ? "bg-discord-text-muted" : "bg-discord-danger"}
                    >
                      {hasEnded ? "Ended" : isActive ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-3 mb-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-discord-text-secondary">Prize</span>
                      <span className="font-medium text-discord-text">{giveaway.prize}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-discord-text-secondary">Entries</span>
                      <span className="font-medium text-discord-text">{giveaway.entries.length}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-discord-text-secondary">Winners</span>
                      <span className="font-medium text-discord-text">
                        {giveaway.winners.length}/{giveaway.winnerCount}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-discord-text-secondary">
                        {hasEnded ? "Ended" : "Ends"}
                      </span>
                      <span className="font-medium text-discord-text">
                        {hasEnded ? getTimeRemaining(giveaway.endsAt) : getTimeRemaining(giveaway.endsAt)}
                      </span>
                    </div>
                  </div>
                  
                  <div className="flex gap-2">
                    <Button 
                      variant="outline" 
                      className="flex-1 bg-discord-tertiary border-discord-bg text-discord-text hover:bg-discord-blurple/20"
                      data-testid={`button-view-entries-${giveaway.id}`}
                    >
                      {hasEnded ? "View Results" : "View Entries"}
                    </Button>
                    {isActive && !hasEnded && (
                      <Button 
                        variant="outline"
                        className="bg-discord-danger hover:bg-red-600 border-discord-danger text-white"
                        onClick={() => handleEndGiveaway(giveaway.id)}
                        data-testid={`button-end-giveaway-${giveaway.id}`}
                      >
                        End Now
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
