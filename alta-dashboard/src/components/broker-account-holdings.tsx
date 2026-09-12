import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { type BrokerAccountSnapshot } from "@/lib/broker-connections";
import { useI18n } from "@/lib/i18n";

/** Broker-reported holdings are not relabelled as ALTA-owned positions. */
export function BrokerAccountHoldings({
  snapshot,
}: {
  snapshot: BrokerAccountSnapshot;
}) {
  const { t, number } = useI18n();
  return (
    <div className="broker-account-holdings">
      {snapshot.positions.length > 0 && (
        <details>
          <summary>
            {t("positions")} · {number(snapshot.positions.length)}
          </summary>
          <Table aria-label={t("positions")}>
            <TableHeader>
              <TableRow>
                <TableHead>{t("symbol")}</TableHead>
                <TableHead>{t("quantity")}</TableHead>
                <TableHead>{t("marketValue")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {snapshot.positions.map((p) => (
                <TableRow key={`${p.symbol}:${p.currency}`}>
                  <TableCell>{p.symbol}</TableCell>
                  <TableCell>{number(Number(p.quantity))}</TableCell>
                  <TableCell>
                    {p.market_value === null
                      ? "—"
                      : number(Number(p.market_value), {
                          style: "currency",
                          currency: p.currency,
                        })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      )}
      {snapshot.orders.length > 0 && (
        <details>
          <summary>
            {t("orders")} · {number(snapshot.orders.length)}
          </summary>
          <Table aria-label={t("orders")}>
            <TableHeader>
              <TableRow>
                <TableHead>{t("symbol")}</TableHead>
                <TableHead>{t("side")}</TableHead>
                <TableHead>{t("quantity")}</TableHead>
                <TableHead>{t("filled")}</TableHead>
                <TableHead>{t("status")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {snapshot.orders.map((o) => (
                <TableRow key={o.order_id}>
                  <TableCell>{o.symbol}</TableCell>
                  <TableCell>
                    {t(o.side === "BUY" ? "brokerOrderBuy" : "brokerOrderSell")}
                  </TableCell>
                  <TableCell>{number(Number(o.quantity))}</TableCell>
                  <TableCell>{number(Number(o.filled))}</TableCell>
                  <TableCell>{t(`brokerOrderState_${o.state}`)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      )}
    </div>
  );
}
