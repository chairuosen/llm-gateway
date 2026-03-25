/**
 * Model Test Dialog
 * Simulates a chat request for a model and returns latency + content.
 * Supports testing all providers in parallel or a specific provider.
 */

'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useModel, useTestModel } from '@/lib/hooks';
import { getApiErrorMessage } from '@/lib/api/error';
import { formatDuration } from '@/lib/utils';
import { getProviderProtocolLabel, useProviderProtocolConfigs } from '@/lib/providerProtocols';
import { ModelMappingProvider, ModelTestResponse, ProtocolType } from '@/types';

interface ModelTestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  requestedModel: string;
}

const ALL_PROVIDERS_VALUE = '__all__';

interface ProviderResult {
  provider: ModelMappingProvider;
  result?: ModelTestResponse;
  error?: string;
  loading: boolean;
}

export function ModelTestDialog({
  open,
  onOpenChange,
  requestedModel,
}: ModelTestDialogProps) {
  const t = useTranslations('models');
  const tCommon = useTranslations('common');
  const [protocol, setProtocol] = useState<ProtocolType | ''>('');
  const [stream, setStream] = useState(false);
  const [selectedProviderId, setSelectedProviderId] = useState<string>(ALL_PROVIDERS_VALUE);
  const [providerResults, setProviderResults] = useState<ProviderResult[]>([]);
  const [singleResult, setSingleResult] = useState<ModelTestResponse | null>(null);
  const [singleError, setSingleError] = useState<string | null>(null);

  const { data: model } = useModel(requestedModel);
  const { configs: protocolConfigs } = useProviderProtocolConfigs();
  const testMutation = useTestModel();

  const availableProtocols = useMemo(() => {
    const hasProviders = (model?.providers?.length ?? 0) > 0;
    if (!hasProviders) {
      return [];
    }
    const supported: ProtocolType[] = [
      'openai',
      'openai_responses',
      'anthropic',
      'gemini',
    ];
    if (protocolConfigs.length === 0) {
      return supported;
    }
    const configured = new Set(protocolConfigs.map((config) => config.protocol));
    return supported.filter((protocol) => configured.has(protocol));
  }, [model?.providers, protocolConfigs]);

  const activeProviders = useMemo(() => {
    return (model?.providers ?? []).filter((p) => p.is_active && p.provider_is_active !== false);
  }, [model?.providers]);

  const allProviders = useMemo(() => {
    return model?.providers ?? [];
  }, [model?.providers]);

  const isBatchMode = selectedProviderId === ALL_PROVIDERS_VALUE;
  const isTesting = isBatchMode
    ? providerResults.some((r) => r.loading)
    : testMutation.isPending;

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSingleResult(null);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSingleError(null);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProviderResults([]);
      if (availableProtocols.length > 0) {
        if (!protocol || !availableProtocols.includes(protocol)) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setProtocol(availableProtocols[0]);
        }
      } else if (protocol) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setProtocol('');
      }
    }
  }, [open, protocol, availableProtocols]);

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      setSingleResult(null);
      setSingleError(null);
      setProviderResults([]);
    }
  };

  const handleTest = async () => {
    if (!protocol) {
      setSingleError(t('testDialog.protocolRequired'));
      return;
    }

    if (isBatchMode) {
      if (activeProviders.length === 0) return;
      // Initialize all rows as loading
      const initialResults: ProviderResult[] = activeProviders.map((p) => ({
        provider: p,
        loading: true,
      }));
      setProviderResults(initialResults);
      setSingleResult(null);
      setSingleError(null);

      // Fire all requests in parallel
      await Promise.all(
        activeProviders.map(async (provider) => {
          try {
            const response = await testMutation.mutateAsync({
              requestedModel,
              data: {
                protocol: protocol as ProtocolType,
                stream,
                provider_id: provider.provider_id,
              },
            });
            setProviderResults((prev) =>
              prev.map((r) =>
                r.provider.provider_id === provider.provider_id
                  ? { ...r, result: response, loading: false }
                  : r
              )
            );
          } catch (err) {
            setProviderResults((prev) =>
              prev.map((r) =>
                r.provider.provider_id === provider.provider_id
                  ? {
                      ...r,
                      error: getApiErrorMessage(err, t('testDialog.testFailed')),
                      loading: false,
                    }
                  : r
              )
            );
          }
        })
      );
    } else {
      setSingleError(null);
      setSingleResult(null);
      setProviderResults([]);
      try {
        const response = await testMutation.mutateAsync({
          requestedModel,
          data: {
            protocol: protocol as ProtocolType,
            stream,
            provider_id: parseInt(selectedProviderId, 10),
          },
        });
        setSingleResult(response);
      } catch (err) {
        setSingleError(getApiErrorMessage(err, t('testDialog.testFailed')));
      }
    }
  };

  const responseText = singleResult?.content ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[900px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('testDialog.title')}</DialogTitle>
          <DialogDescription>
            {t('testDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>{t('testDialog.protocol')}</Label>
            <Select
              value={protocol}
              onValueChange={(value) => setProtocol(value as ProtocolType)}
              disabled={availableProtocols.length === 0}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    availableProtocols.length === 0
                      ? t('testDialog.noProtocols')
                      : t('testDialog.selectProtocol')
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {availableProtocols.map((item) => (
                  <SelectItem key={item} value={item}>
                    {getProviderProtocolLabel(item, protocolConfigs)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {availableProtocols.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                {t('testDialog.addProvidersHint')}
              </p>
            ) : null}
          </div>

          <div className="grid gap-2">
            <Label>{t('testDialog.selectProvider')}</Label>
            <Select
              value={selectedProviderId}
              onValueChange={setSelectedProviderId}
              disabled={allProviders.length === 0}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_PROVIDERS_VALUE}>
                  {t('testDialog.allProviders')}
                </SelectItem>
                {allProviders.map((p) => {
                  const isInactive = !p.is_active || p.provider_is_active === false;
                  return (
                    <SelectItem key={p.provider_id} value={String(p.provider_id)}>
                      <span className={isInactive ? 'text-muted-foreground' : undefined}>
                        {p.provider_name}
                        {isInactive && <span className="ml-1 text-xs opacity-60">({t('testDialog.inactive')})</span>}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <div>
              <Label htmlFor="model-test-stream" className="text-sm">
                {t('testDialog.stream')}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t('testDialog.streamHint')}
              </p>
            </div>
            <Switch
              id="model-test-stream"
              checked={stream}
              onCheckedChange={setStream}
            />
          </div>
        </div>

        {singleError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {singleError}
          </div>
        ) : null}

        {/* Batch results table */}
        {isBatchMode && providerResults.length > 0 ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">{t('testDialog.results')}</p>
            <div className="rounded-md border overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 border-b">
                    <th className="px-3 py-2 text-left font-medium">{t('testDialog.provider')}</th>
                    <th className="px-3 py-2 text-left font-medium">{t('testDialog.targetModel')}</th>
                    <th className="px-3 py-2 text-left font-medium">{t('testDialog.status')}</th>
                    <th className="px-3 py-2 text-left font-medium">{t('testDialog.latency')}</th>
                    <th className="px-3 py-2 text-left font-medium">{t('testDialog.firstToken')}</th>
                    <th className="px-3 py-2 text-left font-medium">{t('testDialog.response')}</th>
                  </tr>
                </thead>
                <tbody>
                  {providerResults.map((row) => (
                    <tr key={row.provider.provider_id} className="border-b last:border-0">
                      <td className="px-3 py-2 font-mono">{row.provider.provider_name}</td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                        {row.result?.target_model ?? row.provider.target_model_name}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {row.loading ? (
                          <span className="text-muted-foreground">{t('testDialog.testing')}</span>
                        ) : row.error ? (
                          <span className="text-destructive">ERR</span>
                        ) : (
                          <span className={row.result && row.result.response_status < 300 ? 'text-green-600' : 'text-destructive'}>
                            {row.result?.response_status ?? '-'}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {row.loading ? '-' : formatDuration(row.result?.total_time_ms ?? null)}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {row.loading ? '-' : formatDuration(row.result?.first_byte_delay_ms ?? null)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs max-w-[200px] truncate">
                        {row.loading ? (
                          <span className="text-muted-foreground">{t('testDialog.testing')}</span>
                        ) : row.error ? (
                          <span className="text-destructive" title={row.error}>{row.error}</span>
                        ) : (
                          <span title={row.result?.content ?? ''}>
                            {row.result?.content?.slice(0, 80) ?? '-'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {/* Single provider result */}
        {!isBatchMode ? (
          <>
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('testDialog.provider')}</span>
                <span className="font-mono">
                  {singleResult?.provider_name ?? '-'}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('testDialog.targetModel')}</span>
                <span className="font-mono">
                  {singleResult?.target_model ?? '-'}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('testDialog.latency')}</span>
                <span className="font-mono">
                  {formatDuration(singleResult?.total_time_ms ?? null)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('testDialog.firstToken')}</span>
                <span className="font-mono">
                  {formatDuration(singleResult?.first_byte_delay_ms ?? null)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t('testDialog.status')}</span>
                <span className="font-mono">
                  {singleResult?.response_status ?? '-'}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">{t('testDialog.response')}</p>
              <Textarea
                rows={8}
                value={responseText}
                readOnly
                placeholder={t('testDialog.noResponse')}
                className="font-mono"
              />
            </div>
          </>
        ) : null}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
          >
            {tCommon('close')}
          </Button>
          <Button
            type="button"
            onClick={handleTest}
            disabled={isTesting || availableProtocols.length === 0}
          >
            {isTesting
              ? isBatchMode
                ? t('testDialog.batchTesting')
                : t('testDialog.testing')
              : tCommon('test')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
