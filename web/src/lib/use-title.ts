import { useEffect } from 'react'

export function useTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · PaperAid` : 'PaperAid — Clear, correct, properly formatted papers'
  }, [title])
}
