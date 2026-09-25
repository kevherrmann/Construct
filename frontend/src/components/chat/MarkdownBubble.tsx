import { Markdown } from './Markdown'
import s from './Message.module.css'

/** Markdown in einer Sprechblase ohne Avatar — z. B. eine Skill-Datei. */
export function MarkdownBubble({ text }: { text: string }) {
  return (
    <div className={s.msg}>
      <Markdown className={s.bubble} text={text} />
    </div>
  )
}
