import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function useOperationLimit() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["key-operation-limit"],
    queryFn: api.getOperationLimit,
    refetchInterval: current => current.state.data?.remaining === 0 ? 1000 : false,
  });

  return {
    operationsBlocked: query.data?.remaining === 0,
    retryAfter: query.data?.retry_after ?? 0,
    refreshOperationLimit: () => queryClient.invalidateQueries({ queryKey: ["key-operation-limit"] }),
  };
}
