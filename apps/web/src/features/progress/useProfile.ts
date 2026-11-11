import { useQuery } from "@tanstack/react-query";
import { api } from "../../shared/api/client";

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: async () => {
      const { data, response } = await api.GET("/api/profile");
      if (!response.ok || data === undefined) {
        throw new Error(`GET /api/profile failed: ${response.status}`);
      }
      return data;
    },
  });
}
