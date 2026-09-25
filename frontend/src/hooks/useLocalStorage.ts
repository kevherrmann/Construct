import { useCallback, useState } from 'react'
import { getItem, setItem } from '@/lib/storage'

export function useLocalStorage(key: string): [string | null, (v: string | null) => void] {
  const [value, setValue] = useState(() => getItem(key))
  const set = useCallback(
    (v: string | null) => {
      setValue(v)
      setItem(key, v)
    },
    [key],
  )
  return [value, set]
}
