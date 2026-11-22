import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { CornerDownLeft, Search } from "lucide-react";
import type { View } from "@/lib/route";
import { cn } from "@/lib/utils";

export interface PaletteView {
  id: View;
  label: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** the screens to jump to */
  views: readonly PaletteView[];
  currentView: View;
  onGo: (view: View) => void;
  /** run the paper search with this text (the app uses the search mode that is currently chosen) */
  onSearch: (text: string) => void;
}

type Item =
  | { kind: "go"; key: string; label: string; view: View; hint: string | null }
  | { kind: "search"; key: string; label: string; text: string; hint: string | null };

/** The items that match what was typed, in their groups. Pure, so it can be tested. */
export function paletteItems(views: readonly PaletteView[], currentView: View, text: string): { go: Item[]; search: Item[] } {
  const q = text.trim();
  const needle = q.toLowerCase();
  const go: Item[] = views
    .filter((v) => !needle || v.label.toLowerCase().includes(needle))
    .map((v) => ({ kind: "go", key: "go-" + v.id, label: v.label, view: v.id, hint: v.id === currentView ? "current" : null }));
  const search: Item[] = q ? [{ kind: "search", key: "search", label: `Search papers for “${q}”`, text: q, hint: null }] : [];
  return { go, search };
}

/**
 * The command palette: a dialog with a search box and two groups of actions, "Go to" (the screens) and "Search papers" (runs
 * the paper search with the typed text and opens the Papers screen). Built on the Radix dialog for the focus trap, Escape and
 * a click outside; the rest is ours: a combobox over a listbox (aria-activedescendant), arrow keys, Home, End and Enter.
 * Its state starts fresh each time it opens, because the content is only mounted while it is open.
 */
export function CommandPalette(props: CommandPaletteProps) {
  return (
    <Dialog.Root open={props.open} onOpenChange={props.onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/55 backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby="palette-desc"
          className="glass fixed top-[14vh] left-1/2 z-[61] w-[min(40rem,92vw)] -translate-x-1/2 overflow-hidden rounded-2xl outline-none"
        >
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Dialog.Description id="palette-desc" className="sr-only">
            Type to search papers or to jump to a screen. Use the arrow keys to move, Enter to choose and Escape to close.
          </Dialog.Description>
          <PaletteBody {...props} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PaletteBody({ views, currentView, onGo, onSearch, onOpenChange }: CommandPaletteProps) {
  const uid = useId();
  const listId = `${uid}-list`;
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const { go, search } = useMemo(() => paletteItems(views, currentView, text), [views, currentView, text]);
  const items = useMemo(() => [...go, ...search], [go, search]);
  const current = Math.min(active, Math.max(0, items.length - 1));
  const optionId = (key: string) => `${uid}-opt-${key}`;

  const run = (item: Item | undefined) => {
    if (!item) return;
    onOpenChange(false);
    if (item.kind === "go") onGo(item.view);
    else onSearch(item.text);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((current + 1) % Math.max(1, items.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((current - 1 + items.length) % Math.max(1, items.length));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(Math.max(0, items.length - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(items[current]);
    }
  };

  const group = (label: string, list: Item[]) =>
    list.length === 0 ? null : (
      <div role="group" aria-labelledby={`${uid}-g-${label.replace(/\s+/g, "-")}`} className="px-2 pb-2">
        <div id={`${uid}-g-${label.replace(/\s+/g, "-")}`} className="mono-label px-2 py-1.5">{label}</div>
        {list.map((item) => {
          const isActive = items[current]?.key === item.key;
          return (
            <div
              key={item.key}
              id={optionId(item.key)}
              role="option"
              aria-selected={isActive}
              onMouseMove={() => setActive(items.findIndex((i) => i.key === item.key))}
              onClick={() => run(item)}
              className={cn(
                "flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive ? "bg-primary/15 text-foreground" : "text-muted",
              )}
            >
              <span className="min-w-0 truncate">{item.label}</span>
              {item.hint ? <span className="mono-label shrink-0 text-[10px]">{item.hint}</span> : isActive ? <CornerDownLeft className="size-3.5 shrink-0" aria-hidden /> : null}
            </div>
          );
        })}
      </div>
    );

  return (
    <div>
      <div className="flex items-center gap-3 border-b border-border px-4">
        <Search className="size-4 shrink-0 text-muted" aria-hidden />
        <input
          ref={inputRef}
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={items[current] ? optionId(items[current]!.key) : undefined}
          aria-label="Search or jump to"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          placeholder="Search or jump to…"
          className="h-14 w-full bg-transparent text-base outline-none placeholder:text-muted"
        />
        <kbd className="mono-label shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px]">esc</kbd>
      </div>
      <div id={listId} role="listbox" aria-label="Commands" data-lenis-prevent className="scroll-thin max-h-[50vh] overflow-y-auto pt-2">
        {group("Go to", go)}
        {group("Search papers", search)}
        {items.length === 0 ? <p className="px-4 py-6 text-center text-sm text-muted">No results.</p> : null}
      </div>
    </div>
  );
}
