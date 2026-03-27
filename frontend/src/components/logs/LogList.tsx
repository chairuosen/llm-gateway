/**
 * Log List Component
 * Displays log data table
 */

'use client';

import React from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  Eye, 
  ArrowRight,
  Waves,
} from 'lucide-react';
import { RequestLog } from '@/types';
import { formatDateTime, getStatusColor, formatUsd, formatDuration } from '@/lib/utils';
import { useTranslations } from 'next-intl';

interface LogListProps {
  /** Log list data */
  logs: RequestLog[];
  /** View details callback */
  onView: (log: RequestLog) => void;
}

/**
 * Log List Component
 */
export function LogList({ logs, onView }: LogListProps) {
  const t = useTranslations('logs');
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[180px]">{t('list.columns.time')}</TableHead>
          <TableHead>{t('list.columns.provider')}</TableHead>
          <TableHead>{t('list.columns.modelMapping')}</TableHead>
          <TableHead>{t('list.columns.timing')}</TableHead>
          <TableHead>{t('list.columns.tokenInOut')}</TableHead>
          <TableHead>{t('list.columns.cost')}</TableHead>
          <TableHead>{t('list.columns.statusRetry')}</TableHead>
          <TableHead className="text-right">{t('list.columns.action')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {logs.map((log) => {
          const statusColor = getStatusColor(log.response_status);
          
          return (
            <TableRow key={log.id} className="group">
              <TableCell className="font-mono text-xs text-muted-foreground">
                <div>{formatDateTime(log.request_time)}</div>
                <div className="mt-1 truncate opacity-0 transition-opacity group-hover:opacity-100" title={log.trace_id}>
                  {log.trace_id?.slice(0, 8)}...
                </div>
              </TableCell>
              <TableCell>{log.provider_name}</TableCell>
              <TableCell>
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-1 font-medium">
                    {log.requested_model}
                    {log.requested_model !== log.target_model && (
                      <>
                        <ArrowRight className="h-3 w-3 text-muted-foreground" suppressHydrationWarning />
                        <span className="text-muted-foreground">
                          {log.target_model}
                        </span>
                      </>
                    )}
                    {log.is_stream && (
                      <span title={t('list.streamRequest')} className="ml-1">
                        <Waves className="h-3 w-3 text-blue-500" suppressHydrationWarning />
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {log.api_key_name}
                  </div>
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs">
                <div className="flex flex-col gap-0.5">
                  <div
                    className="text-muted-foreground"
                    title={t('list.ttfb', { duration: formatDuration(log.first_byte_delay_ms) })}
                  >
                    {formatDuration(log.first_byte_delay_ms)}
                  </div>
                  <div title={t('list.totalTime', { duration: formatDuration(log.total_time_ms) })}>
                    {formatDuration(log.total_time_ms)}
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col text-xs">
                  <span>{t('list.inTokens', { count: log.input_tokens || 0 })}</span>
                  <span className="text-muted-foreground">
                    {t('list.outTokens', { count: log.output_tokens || 0 })}
                  </span>
                  {(log.cache_read_tokens ?? 0) > 0 && (
                    <span className="text-blue-500 opacity-80">
                      {t('list.cacheReadTokens', { count: log.cache_read_tokens ?? 0 })}
                    </span>
                  )}
                  {(log.cache_creation_tokens ?? 0) > 0 && (
                    <span className="text-orange-500 opacity-80">
                      {t('list.cacheCreationTokens', { count: log.cache_creation_tokens ?? 0 })}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell
                className="font-mono text-xs"
                title={t('list.costTooltip', {
                  input: formatUsd(log.input_cost),
                  output: formatUsd(log.output_cost),
                  cacheCreation: formatUsd(log.cache_creation_cost),
                })}
              >
                <div>{formatUsd(log.total_cost)}</div>
                {(log.cache_creation_cost ?? 0) > 0 && (
                  <div className="text-muted-foreground opacity-70">
                    +{formatUsd(log.cache_creation_cost)} cache
                  </div>
                )}
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-start gap-1">
                  {log.status === 'in_progress' ? (
                    <Badge variant="outline" className="animate-pulse border-blue-400 text-blue-600">
                      进行中
                    </Badge>
                  ) : (
                    <Badge variant="outline" className={statusColor}>
                      {log.response_status ?? t('unknown')}
                    </Badge>
                  )}
                  {log.retry_count > 0 && (
                    <span className="text-xs text-orange-500">
                      {t('list.retry', { count: log.retry_count })}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onView(log)}
                  title={t('list.viewDetails')}
                >
                  <Eye className="h-4 w-4" suppressHydrationWarning />
                </Button>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
