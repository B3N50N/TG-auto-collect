USE [TG_recordbot]
GO
/****** Object:  Table [dbo].[chat_record]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[chat_record](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[time] [timestamp] NULL,
	[date] [datetimeoffset](7) NULL,
	[to_id] [varchar](50) NOT NULL,
	[event_type] [varchar](50) NOT NULL,
	[msg_id] [varchar](50) NOT NULL,
	[from_id] [varchar](50) NULL,
	[from_name] [nvarchar](max) NULL,
	[topic] [varchar](50) NULL,
	[msg_type] [varchar](50) NULL,
	[msg] [nvarchar](max) NULL,
	[document_id] [int] NULL,
	[document_afd_chat_id] [varchar](50) NULL,
	[document_afd_chat2_id] [varchar](50) NULL,
 CONSTRAINT [PK_chat_record] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[file_id]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[file_id](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[time] [timestamp] NOT NULL,
	[file_id] [varchar](900) NOT NULL,
	[afd] [int] NOT NULL,
	[rc] [int] NOT NULL,
	[rc_chat] [varchar](50) NULL,
	[rc_msg_id] [varchar](50) NULL,
	[gt] [int] NOT NULL,
	[download] [int] NOT NULL,
 CONSTRAINT [PK_file_id] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[hash]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[hash](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[hash] [varchar](450) NULL,
	[file_id] [varchar](max) NULL,
 CONSTRAINT [PK_id] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [IX_hash_3] UNIQUE NONCLUSTERED 
(
	[hash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[id_name]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[id_name](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[peerid] [varchar](50) NOT NULL,
	[peername] [nvarchar](max) NULL,
 CONSTRAINT [PK_id_name] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[list_af]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[list_af](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[afid] [varchar](50) NOT NULL,
	[afname] [nvarchar](max) NULL,
	[proccess_count] [int] NOT NULL,
	[bot_id] [varchar](50) NULL,
	[media] [int] NOT NULL,
	[link] [int] NOT NULL,
	[fkey] [int] NOT NULL,
	[me] [int] NOT NULL,
	[filter] [int] NOT NULL,
	[dedupe] [int] NOT NULL,
 CONSTRAINT [PK_list_af] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[list_afd_msg_history]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[list_afd_msg_history](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[msg] [nvarchar](max) NULL,
 CONSTRAINT [PK_afd_msg_history] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[list_ext]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[list_ext](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[from_id] [varchar](50) NOT NULL,
	[to_id] [varchar](50) NOT NULL,
	[bot_id] [varchar](50) NOT NULL,
 CONSTRAINT [PK_list_ext] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[list_gt]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[list_gt](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[gtid] [varchar](50) NOT NULL,
	[gtname] [nvarchar](max) NULL,
	[proccess_count] [int] NOT NULL,
	[bot_id] [varchar](50) NULL,
 CONSTRAINT [PK_list_gt] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[list_rc]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[list_rc](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[rcid] [varchar](50) NOT NULL,
	[rcname] [nvarchar](max) NULL,
	[proccess_count] [int] NOT NULL,
	[bot_id] [varchar](50) NULL,
 CONSTRAINT [PK_list_rc] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[RC_summary]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[RC_summary](
	[rid] [int] IDENTITY(1,1) NOT NULL,
	[rcid] [varchar](50) NOT NULL,
	[rcname] [nvarchar](max) NOT NULL,
	[rc_dbname] [varchar](50) NOT NULL,
 CONSTRAINT [PK_RC_summary] PRIMARY KEY CLUSTERED 
(
	[rid] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/****** Object:  Table [dbo].[replace_table]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[replace_table](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[match_str] [nvarchar](200) NOT NULL,
	[replace_str] [nvarchar](200) NULL,
 CONSTRAINT [PK_replace_table] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[template]    Script Date: 2/26/2024 10:44:34 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[template](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[time] [timestamp] NOT NULL,
	[date] [datetimeoffset](7) NULL,
	[event_type] [varchar](50) NOT NULL,
	[msg_id] [varchar](50) NOT NULL,
	[from_id] [varchar](50) NULL,
	[from_name] [nvarchar](max) NULL,
	[topic] [varchar](50) NULL,
	[msg_type] [varchar](50) NULL,
	[msg] [nvarchar](max) NULL,
	[document_id] [int] NULL,
 CONSTRAINT [PK_template] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [IX_chat_record_1]    Script Date: 2/26/2024 10:44:34 AM ******/
CREATE NONCLUSTERED INDEX [IX_chat_record_1] ON [dbo].[chat_record]
(
	[msg_id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
/****** Object:  Index [IX_replace_table]    Script Date: 2/26/2024 10:44:34 AM ******/
CREATE UNIQUE NONCLUSTERED INDEX [IX_replace_table] ON [dbo].[replace_table]
(
	[match_str] ASC,
	[replace_str] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
/****** Object:  Index [IX_chat_record]    Script Date: 2/26/2024 10:44:34 AM ******/
CREATE NONCLUSTERED COLUMNSTORE INDEX [IX_chat_record] ON [dbo].[chat_record]
(
	[to_id]
)WITH (DROP_EXISTING = OFF, COMPRESSION_DELAY = 0, DATA_COMPRESSION = COLUMNSTORE) ON [PRIMARY]
GO
/****** Object:  Index [IX_hash_2]    Script Date: 2/26/2024 10:44:34 AM ******/
CREATE NONCLUSTERED COLUMNSTORE INDEX [IX_hash_2] ON [dbo].[hash]
(
	[hash]
)WITH (DROP_EXISTING = OFF, COMPRESSION_DELAY = 0, DATA_COMPRESSION = COLUMNSTORE) ON [PRIMARY]
GO
/****** Object:  Index [IX_id_name]    Script Date: 2/26/2024 10:44:34 AM ******/
CREATE NONCLUSTERED COLUMNSTORE INDEX [IX_id_name] ON [dbo].[id_name]
(
	[peerid]
)WITH (DROP_EXISTING = OFF, COMPRESSION_DELAY = 0, DATA_COMPRESSION = COLUMNSTORE) ON [PRIMARY]
GO
ALTER TABLE [dbo].[file_id] ADD  CONSTRAINT [DF_file_id_afd]  DEFAULT ((0)) FOR [afd]
GO
ALTER TABLE [dbo].[file_id] ADD  CONSTRAINT [DF_file_id_rc]  DEFAULT ((0)) FOR [rc]
GO
ALTER TABLE [dbo].[file_id] ADD  CONSTRAINT [DF_file_id_gt]  DEFAULT ((0)) FOR [gt]
GO
ALTER TABLE [dbo].[file_id] ADD  CONSTRAINT [DF_file_id_download]  DEFAULT ((1)) FOR [download]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_proccess_count]  DEFAULT ((-1)) FOR [proccess_count]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_media]  DEFAULT ((1)) FOR [media]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_link]  DEFAULT ((1)) FOR [link]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_fkey]  DEFAULT ((1)) FOR [fkey]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_me]  DEFAULT ((1)) FOR [me]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_filter]  DEFAULT ((1)) FOR [filter]
GO
ALTER TABLE [dbo].[list_af] ADD  CONSTRAINT [DF_list_af_dedupe]  DEFAULT ((1)) FOR [dedupe]
GO
ALTER TABLE [dbo].[list_gt] ADD  CONSTRAINT [DF_list_gt_proccess_count]  DEFAULT ((-1)) FOR [proccess_count]
GO
ALTER TABLE [dbo].[list_rc] ADD  CONSTRAINT [DF_list_rc_proccess_count]  DEFAULT ((-1)) FOR [proccess_count]
GO
ALTER TABLE [dbo].[template] ADD  CONSTRAINT [DF_template_date]  DEFAULT ('1900-01-01 00:01:01') FOR [date]
GO
