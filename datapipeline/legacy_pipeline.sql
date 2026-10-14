-- =====================================================================
--  JOB      : PRVSUM01
--  DESC     : PROVIDER MONTHLY CLAIM SUMMARY - NIGHTLY BATCH
--  INPUT    : CLM, PROV
--  OUTPUT   : RPT_PROV_SUM
--  SCHEDULE : NIGHTLY 02:00 VIA RUN_LEGACY.SH
--  AUTHOR   : R.K.   03/14/2011
--  MODS     : 08/02/2014  J.T.  ADDED 'OT' CATEGORY FOR NON IP/OP BILLS
--             05/21/2016  R.K.  HOSPICE SPLIT REMOVED PER OPS (SEE STEP 2)
--             11/19/2017  R.K.  EXCLUDE VOIDS PER OPS REQUEST #4471
--             02/03/2019  M.P.  TIMELY FILING CHECK ADDED (STEP 3)
-- =====================================================================

-- ---------------------------------------------------------------------
--  STEP 1 : BUILD CLAIM STAGING
--           DROP REJECTS (R) AND VOIDS (V)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS TMP_CLM_STG;

CREATE TABLE TMP_CLM_STG AS
SELECT  C.CLM_ID,
        C.PROV_NPI,
        P.PROV_NM,
        C.BILL_TYP,
        C.SVC_FROM_DT,
        C.SVC_THRU_DT,
        C.RCVD_DT,
        C.CLM_CHRG_AMT,
        C.CLM_ALWD_AMT,
        C.PT_RESP_AMT,
        C.CLM_STS_CD,
        SUBSTR(C.SVC_FROM_DT, 1, 6)                          AS RPT_MTH,
        CASE WHEN SUBSTR(C.BILL_TYP, 1, 2) = '11' THEN 'IP'
             WHEN SUBSTR(C.BILL_TYP, 1, 2) = '13' THEN 'OP'
             ELSE 'OT'
        END                                                  AS CLM_CAT,
        CASE WHEN C.CLM_ALWD_AMT < C.CLM_CHRG_AMT
             THEN 'Y' ELSE 'N'
        END                                                  AS TMP_ADJ_FLG,
        (C.CLM_ALWD_AMT - C.PT_RESP_AMT)                     AS NET_PD_AMT,
        JULIANDAY(SUBSTR(C.RCVD_DT, 1, 4)     || '-' ||
                  SUBSTR(C.RCVD_DT, 5, 2)     || '-' ||
                  SUBSTR(C.RCVD_DT, 7, 2))
      - JULIANDAY(SUBSTR(C.SVC_FROM_DT, 1, 4) || '-' ||
                  SUBSTR(C.SVC_FROM_DT, 5, 2) || '-' ||
                  SUBSTR(C.SVC_FROM_DT, 7, 2))               AS RCV_LAG_DYS
FROM    CLM  C
        INNER JOIN PROV P
                ON P.PROV_NPI = C.PROV_NPI
WHERE   C.CLM_STS_CD NOT IN ('R', 'V');

-- ---------------------------------------------------------------------
--  STEP 2 : HOSPICE SPLIT  ** DISABLED 05/21/2016 - DO NOT RE-ENABLE **
-- ---------------------------------------------------------------------
-- UPDATE TMP_CLM_STG
--    SET CLM_CAT = 'HS'
--  WHERE SUBSTR(BILL_TYP, 1, 2) IN ('81', '82');

-- ---------------------------------------------------------------------
--  STEP 3 : TIMELY FILING - REMOVE CLAIMS RECEIVED > 1 YR AFTER SERVICE
-- ---------------------------------------------------------------------
DELETE FROM TMP_CLM_STG
 WHERE RCV_LAG_DYS > 365;

-- ---------------------------------------------------------------------
--  STEP 4 : BUILD REPORT TABLE
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS RPT_PROV_SUM;

CREATE TABLE RPT_PROV_SUM AS
SELECT  PROV_NPI,
        PROV_NM,
        RPT_MTH,
        CLM_CAT,
        COUNT(*)                          AS CLM_CNT,
        ROUND(SUM(CLM_CHRG_AMT), 2)       AS TOT_CHRG,
        ROUND(SUM(CLM_ALWD_AMT), 2)       AS TOT_ALWD,
        ROUND(SUM(NET_PD_AMT), 2)         AS TOT_PD
FROM    TMP_CLM_STG
GROUP BY PROV_NPI, PROV_NM, RPT_MTH, CLM_CAT
ORDER BY PROV_NPI, RPT_MTH, CLM_CAT;

-- END OF JOB PRVSUM01
