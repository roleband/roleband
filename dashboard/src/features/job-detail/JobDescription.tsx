import { useRef } from "react";
import type { JobDescriptionSection } from "../../api";
import {
  roleJobDescriptionNoDescriptionCaptured,
} from "../../copy/gen/role";
import { ownHeading } from "../../copy/vocab";
import { Content } from "../../ui/Content";
import { shapeBlocks } from "./descriptionShape";
import { useStuckHeadings } from "./stuckHeadings";

const LIST_SECTIONS = new Set(["minimum_qualifications", "preferred_qualifications"]);

export function JobDescription({
  sections,
  fallback,
}: {
  sections?: JobDescriptionSection[];
  fallback?: string | null;
}) {
  const list = useRef<HTMLDivElement>(null);
  useStuckHeadings(list, sections);
  if (!sections?.length) {
    if (fallback) return <div className="jd jd-fallback"><Content text={fallback} /></div>;
    return <p className="jd-empty">{roleJobDescriptionNoDescriptionCaptured()}</p>;
  }

  return (
    <div className="jd-sections" ref={list}>
      {sections.map((section, index) => (
        <section className={`jd-section jd-section-${section.key}`} key={`${section.key}-${index}`}>
          <h2>{ownHeading(section.key, section.title) ?? <Content text={section.title} />}</h2>
          {LIST_SECTIONS.has(section.key) ? (
            <ul>
              {section.content
                .split(/\n+/)
                .map((line) => line.trim())
                .filter(Boolean)
                .map((line, lineIndex) => <li key={lineIndex}><Content text={line} /></li>)}
            </ul>
          ) : (
            shapeBlocks(section.content).map((block, blockIndex) => {
              if (block.kind === "heading") return <h3 key={blockIndex}><Content text={block.text} /></h3>;
              if (block.kind === "list") {
                return (
                  <ul key={blockIndex}>
                    {block.items.map((item, itemIndex) => <li key={itemIndex}><Content text={item} /></li>)}
                  </ul>
                );
              }
              return (
                <p key={blockIndex}>
                  {block.lines.map((line, lineIndex) => (
                    <span key={lineIndex}>
                      {lineIndex > 0 && <br />}
                      <Content text={line} />
                    </span>
                  ))}
                </p>
              );
            })
          )}
        </section>
      ))}
    </div>
  );
}
