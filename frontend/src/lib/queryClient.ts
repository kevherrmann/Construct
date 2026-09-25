import { QueryClient } from '@tanstack/react-query'

// Eine Instanz für die ganze App — auch Stores außerhalb von React
// (z. B. der Chat nach einem Lauf) laden darüber Listen neu.
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})
