import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { insertFormSchema } from "@shared/schema";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Plus, Edit, Trash2 } from "lucide-react";
import { z } from "zod";
import type { Guild, Form as FormType } from "@shared/schema";

interface FormsProps {
  guild: Guild;
}

const formFormSchema = insertFormSchema.omit({});

type FormFormData = z.infer<typeof formFormSchema>;

export default function Forms({ guild }: FormsProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const { data: forms = [], isLoading } = useQuery<FormType[]>({
    queryKey: ['/api/guilds', guild.id, 'forms'],
  });

  const createFormMutation = useMutation({
    mutationFn: (data: FormFormData) => apiRequest('POST', `/api/guilds/${guild.id}/forms`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'forms'] });
      setIsCreateModalOpen(false);
      toast({
        title: "Form created",
        description: "The form has been created successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to create form.",
        variant: "destructive",
      });
    },
  });

  const deleteFormMutation = useMutation({
    mutationFn: (formId: string) => apiRequest('DELETE', `/api/forms/${formId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/guilds', guild.id, 'forms'] });
      toast({
        title: "Form deleted",
        description: "The form has been deleted successfully.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to delete form.",
        variant: "destructive",
      });
    },
  });

  const form = useForm<FormFormData>({
    resolver: zodResolver(formFormSchema),
    defaultValues: {
      name: "",
      description: "",
      questions: [],
      responses: [],
      isActive: true,
    },
  });

  const onSubmit = (data: FormFormData) => {
    createFormMutation.mutate(data);
  };

  const handleDeleteForm = (formId: string) => {
    if (window.confirm("Are you sure you want to delete this form? This action cannot be undone.")) {
      deleteFormMutation.mutate(formId);
    }
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
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Form Management</h2>
        <p className="text-discord-text-secondary">Create custom forms and view responses</p>
      </div>
      
      <div className="mb-6">
        <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
          <DialogTrigger asChild>
            <Button 
              className="bg-discord-blurple hover:bg-discord-dark-blurple"
              data-testid="button-create-form"
            >
              <Plus className="h-4 w-4 mr-2" />
              Create Form
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-discord-secondary border-discord-tertiary max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-discord-text">Create New Form</DialogTitle>
            </DialogHeader>
            
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-discord-text">Form Name</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="Enter form name" 
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
                          placeholder="Form description" 
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
                  name="isActive"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between">
                      <FormLabel className="text-discord-text">Active Form</FormLabel>
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
                    disabled={createFormMutation.isPending}
                    data-testid="button-submit-form"
                  >
                    {createFormMutation.isPending ? "Creating..." : "Create Form"}
                  </Button>
                </div>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {forms.length === 0 ? (
          <div className="col-span-full text-center py-8 text-discord-text-muted">
            <p>No forms found</p>
            <p className="text-sm mt-1">Create your first form to get started</p>
          </div>
        ) : (
          forms.map((formItem) => (
            <Card key={formItem.id} className="bg-discord-secondary border-discord-tertiary">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg font-semibold mb-1 text-discord-text">
                      {formItem.name}
                    </CardTitle>
                    {formItem.description && (
                      <p className="text-discord-text-secondary text-sm">{formItem.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button 
                      variant="ghost" 
                      size="sm"
                      className="text-discord-text-secondary hover:text-discord-text"
                      data-testid={`button-edit-form-${formItem.id}`}
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button 
                      variant="ghost" 
                      size="sm"
                      className="text-discord-danger hover:text-red-400"
                      onClick={() => handleDeleteForm(formItem.id)}
                      data-testid={`button-delete-form-${formItem.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent>
                <div className="space-y-2 mb-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-discord-text-secondary">Questions</span>
                    <span className="font-medium text-discord-text">{formItem.questions.length}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-discord-text-secondary">Responses</span>
                    <span className="font-medium text-discord-text">{formItem.responses.length}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-discord-text-secondary">Status</span>
                    <Badge 
                      variant={formItem.isActive ? "default" : "secondary"}
                      className={formItem.isActive ? "bg-discord-success" : "bg-discord-warning"}
                    >
                      {formItem.isActive ? "Active" : "Paused"}
                    </Badge>
                  </div>
                </div>
                
                <Button 
                  variant="outline" 
                  className="w-full bg-discord-tertiary border-discord-bg text-discord-text hover:bg-discord-blurple/20"
                  data-testid={`button-view-responses-${formItem.id}`}
                >
                  View Responses
                </Button>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
