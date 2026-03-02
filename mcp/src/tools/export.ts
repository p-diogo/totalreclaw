import { TotalReclaw } from '@totalreclaw/client';
import { EXPORT_TOOL_DESCRIPTION } from '../prompts.js';

export interface ExportInput {
  format?: 'markdown' | 'json';
  namespace?: string;
  include_metadata?: boolean;
}

export interface ExportOutput {
  content: string;
  format: string;
  fact_count: number;
  exported_at: string;
}

export const exportToolDefinition = {
  name: 'totalreclaw_export',
  description: EXPORT_TOOL_DESCRIPTION,
  inputSchema: {
    type: 'object',
    properties: {
      format: {
        type: 'string',
        enum: ['markdown', 'json'],
        default: 'markdown',
        description: 'Output format',
      },
      namespace: {
        type: 'string',
        description: 'Export only specific namespace',
      },
      include_metadata: {
        type: 'boolean',
        default: true,
        description: 'Include metadata in export',
      },
    },
  },
  annotations: {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
  },
};

export async function handleExport(
  client: TotalReclaw,
  args: unknown,
  defaultNamespace: string
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const input = (args || {}) as ExportInput;
  const format = input.format || 'markdown';
  const includeMetadata = input.include_metadata !== false;

  try {
    const results = await client.recall('*', 1000);
    const ns = input.namespace || defaultNamespace;

    const filtered = ns !== 'default'
      ? results.filter(r => r.fact.metadata.tags?.includes(`namespace:${ns}`))
      : results;

    const exportedAt = new Date().toISOString();

    let content: string;
    if (format === 'json') {
      const jsonData = {
        version: '1.0.0',
        exported_at: exportedAt,
        namespace: ns,
        facts: filtered.map(r => ({
          id: r.fact.id,
          text: r.fact.text,
          importance: Math.round((r.fact.metadata.importance ?? 0.5) * 10),
          created_at: r.fact.createdAt.toISOString(),
          ...(includeMetadata && {
            metadata: {
              tags: r.fact.metadata.tags,
              source: r.fact.metadata.source,
            },
          }),
        })),
      };
      content = JSON.stringify(jsonData, null, 2);
    } else {
      const lines: string[] = [
        `# TotalReclaw Export`,
        ``,
        `**Exported:** ${exportedAt}`,
        `**Namespace:** ${ns}`,
        `**Total Facts:** ${filtered.length}`,
        ``,
        `---`,
        ``,
      ];

      for (const r of filtered) {
        const importance = Math.round((r.fact.metadata.importance ?? 0.5) * 10);
        lines.push(`## ${r.fact.text}`);
        lines.push(``);
        if (includeMetadata) {
          lines.push(`- **Importance:** ${importance}/10`);
          lines.push(`- **Created:** ${r.fact.createdAt.toISOString()}`);
          if (r.fact.metadata.tags?.length) {
            lines.push(`- **Tags:** ${r.fact.metadata.tags.join(', ')}`);
          }
        }
        lines.push(``);
        lines.push(`ID: \`${r.fact.id}\``);
        lines.push(``);
        lines.push(`---`);
        lines.push(``);
      }

      content = lines.join('\n');
    }

    const result: ExportOutput = {
      content,
      format,
      fact_count: filtered.length,
      exported_at: exportedAt,
    };

    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result),
      }],
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error occurred';
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          content: '',
          format,
          fact_count: 0,
          exported_at: new Date().toISOString(),
          error: `Failed to export memories: ${message}`,
        }),
      }],
    };
  }
}
